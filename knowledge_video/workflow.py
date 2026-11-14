from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import jsonschema

from narration_video.core import file_hash, load_project, normalized
from narration_video.voice import OmniVoice

from . import prompts
from .decks import (
    existing_deck,
    normalize_lesson_ids,
    validate_generated_html,
    validate_lesson,
)
from .languages import language_instruction
from .materials import bundle_html, fetch_source, inspect_slides
from .models import (
    DeckOutput,
    Lesson,
    ResearchPlan,
    Review,
    SpeechReview,
    VisualReview,
)
from .providers import Provider
from .runtime import Cancelled, atomic_json, run_process
from .media_providers import get_image_provider
from .media_rights import MediaRightsRegistry
from .run_state import RunStore, fingerprint_inputs
from .semantic_timeline import build_semantic_timeline
from .visuals import auto_fill_secondary_visuals


class Workflow:
    def __init__(self, root, request, notify, cancel):
        self.root = Path(root)
        self.request = request
        self.notify = notify
        self.cancel = cancel
        self.provider = Provider(request.provider, self.root, cancel, notify)
        self.env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent)
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        }

    def step(self, name, message):
        if self.cancel.is_set():
            raise Cancelled("任务已取消")
        self.notify(message, stage=name)

    def llm(self, name, instruction, payload, model, images=None):
        target = self.root / (name + ".json")
        fingerprint_target = self.root / (name + ".fingerprint.json")
        current_fingerprint = fingerprint_inputs(
            {
                "instruction": instruction,
                "payload": payload,
                "schema": getattr(model, "model_json_schema", lambda: {})(),
                "model": getattr(self.request.provider, "model", ""),
                "provider_kind": getattr(self.request.provider, "kind", ""),
                "temperature": getattr(self.request.provider, "temperature", None),
                "images": images,
            }
        )
        if target.exists() and fingerprint_target.exists():
            try:
                saved = json.loads(fingerprint_target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                saved = {}
            if saved.get("fingerprint") == current_fingerprint:
                try:
                    return model.model_validate_json(target.read_text(encoding="utf-8"))
                except Exception:
                    pass
        self.notify("模型正在处理 " + name)
        error = None
        for attempt in range(self.request.max_repairs + 1):
            try:
                answer = self.provider.generate(
                    instruction + language_instruction(self.request.language),
                    {**payload, "previous_error": error},
                    model,
                    images,
                )
                atomic_json(target, answer.model_dump())
                atomic_json(fingerprint_target, {"fingerprint": current_fingerprint})
                return answer
            except (ValueError, KeyError, TypeError, jsonschema.ValidationError) as e:
                error = str(e)
        raise RuntimeError("模型输出未通过结构校验：" + str(error))

    def run(self):
        r = self.request
        p = self.root
        self.step("preflight", "检查本地语音和渲染环境")
        for tool in ("ffmpeg", "ffprobe", "node"):
            if not shutil.which(tool):
                raise RuntimeError("缺少依赖 " + tool + "，请按 README 安装")
        if not Path(r.chrome or chrome_path()).is_file():
            raise RuntimeError("未找到 Chrome / Chromium，请在设置中填写路径")
        OmniVoice({"base_url": r.voice_url}).wait_ready()
        self.step("research", "整理学习目标与资料")
        info = inspect_slides(r.slides_path) if r.slides_mode == "existing" else None
        plan = self.llm(
            "research_plan",
            prompts.RESEARCH,
            {
                "topic": r.topic,
                "audience": r.audience,
                "minutes": r.minutes,
                "source_notes": r.source_notes,
                "existing_slides": info["slides"] if info else None,
            },
            ResearchPlan,
        )
        if (p / "sources.json").exists():
            sources = json.loads((p / "sources.json").read_text())
        else:
            sources = []
            errors = []
            urls = list(dict.fromkeys(r.reference_urls + plan.candidate_urls))[:8]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(fetch_source, url): url for url in urls}
                for future, url in futures.items():
                    try:
                        sources.append(
                            {"id": f"S{len(sources) + 1}", **future.result()}
                        )
                    except Exception as exc:
                        errors.append({"url": url, "error": str(exc)[:300]})
            if r.source_notes:
                sources.append(
                    {
                        "id": "U1",
                        "title": "用户提供的资料",
                        "url": "",
                        "text": r.source_notes,
                        "sha256": hashlib.sha256(r.source_notes.encode()).hexdigest(),
                    }
                )
            if info:
                sources.append(
                    {
                        "id": "D1",
                        "title": "用户提供的已有课件",
                        "url": "",
                        "text": "\n".join(s["text"] for s in info["slides"]),
                        "sha256": file_hash(Path(info["path"])),
                    }
                )
            atomic_json(p / "source_errors.json", errors)
            atomic_json(p / "sources.json", sources)
        knowledge_basis = "reference_materials" if sources else "general_knowledge"
        if not sources:
            self.notify("未提供或获取参考资料，按通用知识与明确标注的教学算例继续")
        atomic_json(
            p / "research_basis.json",
            {
                "mode": knowledge_basis,
                "source_count": len(sources),
                "fetched_source_count": sum(bool(s.get("url")) for s in sources),
                "externally_verified": False,
            },
        )
        context = {
            "topic": r.topic,
            "audience": r.audience,
            "minutes": r.minutes,
            "plan": plan.model_dump(),
            "sources": sources,
            "knowledge_basis": knowledge_basis,
            "existing_slides": info["slides"] if info else None,
        }
        self.step("script", "撰写口播并审查事实和教学顺序")
        lesson = self.llm("lesson_draft", prompts.WRITE, context, Lesson)
        review = self.llm(
            "editor_review",
            prompts.REVIEW,
            {**context, "lesson": lesson.model_dump()},
            Review,
        )
        if not review.approved:
            raise RuntimeError("内容审查未通过：" + "；".join(review.issues))
        lesson, id_changes = normalize_lesson_ids(review.lesson)
        atomic_json(p / "id_normalization.json", {"changes": id_changes})
        if id_changes:
            self.notify(f"已自动规范 {len(id_changes)} 个段落编号，保留原始讲稿和页面对应关系")
        if not sources:
            notice = "本课依据模型通用知识编写，未使用外部核验资料。"
            if notice not in lesson.uncertainties:
                lesson.uncertainties.append(notice)
        validate_lesson(lesson, info)
        valid_sources = {s["id"] for s in sources}
        if any(set(b.source_ids) - valid_sources for b in lesson.blocks):
            raise ValueError("讲稿引用了不存在的资料编号")
        atomic_json(p / "lesson.json", lesson.model_dump())
        _provider_name, _provider = get_image_provider("local", "procedural")
        semantic_timeline = build_semantic_timeline(lesson.blocks)
        atomic_json(p / "semantic_timeline.json", semantic_timeline)
        media_rights = MediaRightsRegistry()
        auto_fill_secondary_visuals(
            semantic_timeline,
            registry=media_rights,
            output_dir=p / "build" / "generated",
            visual_config=r.visual,
        )
        atomic_json(p / "media_rights.json", media_rights.to_dict())
        RunStore(p).start({"request": r.model_dump()})
        RunStore(p).record_stage("lesson", artifacts={"lesson.json": p / "lesson.json"})
        (p / "narration.md").write_text(
            "# "
            + lesson.title
            + "\n\n"
            + "\n\n".join(
                "## " + b.id + "\n[[" + b.id + "]]" + b.narration for b in lesson.blocks
            ),
            encoding="utf-8",
        )
        (p / "script.md").write_text(
            "# "
            + lesson.title
            + "\n\n"
            + "\n\n".join(b.narration for b in lesson.blocks),
            encoding="utf-8",
        )
        self.step("slides", "生成或适配 HTML 课件")
        if info:
            states = existing_deck(info, p / "slides.html")
        else:
            states = {
                b.slide_id: {"slide": b.slide_id, "visible": [], "highlight": None}
                for b in lesson.blocks
            }
        template = (
            Path(r.template_path).expanduser()
            if r.template_path
            else Path(__file__).parent / "templates/default.html"
        )
        template_context = {}
        expected_background = None
        expected_presenter = None
        expected_logo_height = None
        if not info:
            template_raw = bundle_html(template, p / "template.html")
            template_css = "\n".join(
                f.read_text() for f in sorted((p / "assets").glob("*.css"))
            )[:100000]
            template_context = {
                "template_html": template_raw,
                "template_css": template_css,
            }
            color = re.search(
                r"--r-background-color\s*:\s*(#[0-9a-fA-F]{3,8})", template_css
            )
            if color:
                expected_background = color.group(1)
            presenter = re.search(r"Presented by\s+([^<\n]+)", template_raw)
            if presenter:
                expected_presenter = presenter.group(0).strip()
            logo = re.search(r"#logo\s+img\s*\{[^}]*height\s*:\s*(\d+)px", template_raw)
            if logo:
                expected_logo_height = int(logo.group(1))
            deck = self.llm(
                "deck",
                prompts.DECK,
                {"lesson": lesson.model_dump(), **template_context},
                DeckOutput,
            )
            for attempt in range(r.max_repairs + 1):
                try:
                    validate_generated_html(deck.html, lesson)
                    break
                except ValueError as exc:
                    if attempt == r.max_repairs:
                        raise
                    deck = self.llm(
                        "deck_structure_repair_" + str(attempt),
                        prompts.DECK,
                        {
                            "lesson": lesson.model_dump(),
                            **template_context,
                            "previous_html": deck.html,
                            "problems": str(exc),
                        },
                        DeckOutput,
                    )
            (p / "slides.html").write_text(deck.html, encoding="utf-8")
        cfg = {
            "title": lesson.title,
            "notice": "知识视频 · 本人授权克隆声音",
            "script": "narration.md",
            "deck": "slides.html",
            "build_dir": "build",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "playback_speed": r.playback_speed,
            "pause_between_blocks": 0.45,
            "voice": {
                "base_url": r.voice_url,
                "model": "omnivoice",
                "mode": "clone",
                "profile_id": r.profile_id,
                "language": r.language,
                "reference_language": r.reference_language,
                "speed": 1.0,
                "timeout_seconds": 900,
                "backend": r.voice_backend,
            },
            "alignment": {
                "language": r.language,
                "device": "cpu",
                "threads": 4,
                "min_char_score": 0.1,
                "min_coverage": 0.9,
                "min_cue_score": 0.15,
            },
            "asr_model": r.asr_model,
            "subtitle": {
                "font_size": 48,
                "max_chars": 25 if r.language in ("zh", "ja", "ko") else 52,
                "bottom": 50,
            },
            "cues": {b.id: states[b.slide_id] for b in lesson.blocks},
        }
        if r.chrome:
            cfg["chrome"] = r.chrome
        if r.subtitle_font:
            cfg["subtitle"]["font"] = r.subtitle_font
        atomic_json(p / "project.json", cfg)
        self.step("visual_review", "检查课件版式与内容对应")
        for attempt in range(r.max_repairs + 1):
            current = load_project(p / "project.json")
            current["build"].mkdir(exist_ok=True)
            timeline = {
                "initial_state": next(iter(cfg["cues"].values())),
                "events": [{"state": v} for v in cfg["cues"].values()],
            }
            try:
                # Renderer runs as a child so cancel/timeouts also stop Chrome.
                preview = p / "preview.json"
                atomic_json(
                    preview,
                    {
                        "deck": str(p / "slides.html"),
                        "output": str(p / "build/slides"),
                        "width": 1920,
                        "height": 1080,
                        "chrome": r.chrome or chrome_path(),
                        "layoutReport": str(p / "build/layout_report.json"),
                        "expectedBackground": expected_background,
                        "expectedPresenter": expected_presenter,
                        "expectedLogoHeight": expected_logo_height,
                        "states": [timeline["initial_state"]]
                        + [e["state"] for e in timeline["events"]],
                    },
                )
                run_process(
                    [
                        "node",
                        Path(__file__).parent.parent
                        / "narration_video/render_deck.mjs",
                        preview,
                    ],
                    p,
                    self.cancel,
                    180,
                    log=self.notify,
                )
                reports = json.loads((p / "build/layout_report.json").read_text())
                geometry = [issue for page in reports for issue in page["issues"]]
                if geometry:
                    raise ValueError(str(geometry))
                shots = sorted((p / "build/slides").glob("*.png"))
                images = [shots[0], shots[len(shots) // 2], shots[-1]]
                visual = self.llm(
                    "visual_review_" + str(attempt),
                    prompts.VISUAL
                    if r.provider.kind == "codex" or r.provider.vision
                    else prompts.STRUCTURE,
                    {
                        "lesson": lesson.model_dump(),
                        "html": (p / "slides.html").read_text(),
                        **template_context,
                        "geometry": reports,
                        "screenshots_available": r.provider.kind == "codex"
                        or r.provider.vision,
                    },
                    VisualReview,
                    images,
                )
                errors = geometry + visual.issues
                if not geometry and visual.approved:
                    break
                raise ValueError(str(errors))
            except (ValueError, RuntimeError) as exc:
                if info or attempt == r.max_repairs:
                    raise
                deck = self.llm(
                    "deck_repair_" + str(attempt),
                    prompts.DECK,
                    {
                        "lesson": lesson.model_dump(),
                        **template_context,
                        "previous_html": (p / "slides.html").read_text(),
                        "problems": str(exc)[-5000:],
                    },
                    DeckOutput,
                )
                validate_generated_html(deck.html, lesson)
                (p / "slides.html").write_text(deck.html, encoding="utf-8")
        self.step("voice", "准备参考声音")
        service = OmniVoice(cfg["voice"])
        service.wait_ready()
        profile_file = p / "voice_profile.json"
        if not r.profile_id:
            if profile_file.exists():
                profile = json.loads(profile_file.read_text())
            else:
                voice = Path(r.voice_path).expanduser()
                if not voice.is_file():
                    raise ValueError("参考录音不存在，请上传录音或填写有效路径")
                reference = p / "reference"
                reference.mkdir(exist_ok=True)
                if r.reference_text:
                    from .media import prepare_reference

                    prepare_reference(str(voice), reference)
                    (reference / "reference.txt").write_text(
                        r.reference_text, encoding="utf-8"
                    )
                elif not (reference / "reference.txt").exists():
                    run_process(
                        [
                            sys.executable,
                            "-m",
                            "knowledge_video.media",
                            "reference",
                            voice,
                            "--output",
                            reference,
                            "--language",
                            r.reference_language,
                            "--asr-model",
                            r.asr_model,
                        ],
                        p,
                        self.cancel,
                        600,
                        log=self.notify,
                        env=self.env,
                    )
                profile = service.import_voice(
                    reference / "reference.wav",
                    (reference / "reference.txt").read_text(),
                    "Knowledge Studio " + p.name[:8],
                )
                atomic_json(profile_file, profile)
            cfg["voice"]["profile_id"] = profile["id"]
            atomic_json(p / "project.json", cfg)
        self.step("production", "合成配音、逐字对齐并导出视频")
        run_process(
            [
                sys.executable,
                "-m",
                "knowledge_video.media",
                "produce",
                p / "project.json",
                "--repairs",
                r.max_repairs,
            ],
            p,
            self.cancel,
            14400,
            log=self.notify,
            env=self.env,
        )
        self.step("speech_review", "转写复核，检查整句遗漏和数字")
        for attempt in range(r.max_repairs + 1):
            run_process(
                [
                    sys.executable,
                    "-m",
                    "knowledge_video.media",
                    "transcribe",
                    p / "project.json",
                ],
                p,
                self.cancel,
                3600,
                log=self.notify,
                env=self.env,
            )
            rows = json.loads((p / "build/speech_asr.json").read_text())
            check = self.llm(
                "speech_review_" + str(attempt),
                prompts.SPEECH,
                {"blocks": rows},
                SpeechReview,
            )
            if not check.rerecord_ids:
                break
            if set(check.rerecord_ids) - {b.id for b in lesson.blocks}:
                raise ValueError("语音复核返回了不存在的段落")
            if attempt == r.max_repairs:
                raise RuntimeError(
                    "语音复核在多次重做后仍发现问题：" + "；".join(check.notes)
                )
            texts = {b.narration for b in lesson.blocks if b.id in check.rerecord_ids}
            rejected = p / "build/rejected/speech_review" / str(attempt)
            rejected.mkdir(parents=True, exist_ok=True)
            for metadata in (p / "build/voice_cache").glob("*.json"):
                if json.loads(metadata.read_text())["request"]["input"] in texts:
                    for f in (metadata, metadata.with_suffix(".wav")):
                        if f.exists():
                            shutil.move(f, rejected / f.name)
            self.notify("转写复核要求重做：" + ", ".join(check.rerecord_ids))
            run_process(
                [
                    sys.executable,
                    "-m",
                    "knowledge_video.media",
                    "produce",
                    p / "project.json",
                    "--repairs",
                    r.max_repairs,
                ],
                p,
                self.cancel,
                14400,
                log=self.notify,
                env=self.env,
            )
        self.step("delivery", "核对成片与字幕，整理下载文件")
        timeline = json.loads((p / "build/timeline.json").read_text())
        report = json.loads((p / "build/export_report.json").read_text())
        expected = normalized("".join(b.narration for b in lesson.blocks))
        actual = normalized("".join(x["text"] for x in timeline["subtitles"]))
        if expected != actual:
            raise ValueError("字幕未完整覆盖口播稿")
        chapters = [
            {
                "time": e["time"],
                "title": next(b.headline for b in lesson.blocks if b.id == e["id"]),
            }
            for e in timeline["events"]
        ]
        atomic_json(p / "chapters.json", chapters)
        atomic_json(
            p / "quality.json",
            {
                "technical_passed": True,
                "visual_review_mode": "images"
                if r.provider.kind == "codex" or r.provider.vision
                else "html_only",
                "duration": report["duration"],
                "subtitle_characters_match": True,
                "sources": len(sources),
                "knowledge_basis": knowledge_basis,
                "language": r.language,
                "asr_model": r.asr_model,
                "uncertainties": lesson.uncertainties,
                "human_listening_review": "recommended",
                "video_sha256": file_hash(p / "build/video.mp4"),
            },
        )
        desc = (
            "# "
            + lesson.title
            + "\n\n"
            + lesson.description
            + "\n\n## 参考资料\n\n"
            + (
                "\n".join(
                    "- " + s["title"] + (" " + s["url"] if s["url"] else "")
                    for s in sources
                )
                if sources
                else "本课依据模型通用知识编写，未使用外部核验资料。"
            )
            + "\n\n## 章节\n\n"
            + "\n".join(
                f"{int(c['time']) // 60:02d}:{int(c['time']) % 60:02d} {c['title']}"
                for c in chapters
            )
        )
        (p / "description.md").write_text(desc, encoding="utf-8")
        try:
            publication = self.make_publication()
            self.notify("封面与简介已生成", publication=publication,
                        publishing={"status": "completed", "message": "封面与简介已生成"})
        except Cancelled:
            raise
        except Exception as exc:
            # A publishing-asset failure must not discard an already checked video.
            self.notify("视频已完成，封面与简介可单独重试", publishing={
                "status": "failed", "message": str(exc)[-1000:]})
        return {
            "title": lesson.title,
            "duration": report["duration"],
            "chapters": chapters,
            "quality": "技术检查通过；建议发布前完整试听",
        }

    def make_publication(self):
        from .publishing import generate

        self.notify("生成封面文案与视频简介")
        return generate(self)


def chrome_path():
    return (
        os.environ.get("CHROME_BIN")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
