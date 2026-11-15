import re
from pathlib import Path

from .materials import bundle_html

BLOCK_ID = re.compile(r"[a-z][a-z0-9_]{0,40}")


def normalize_lesson_ids(lesson):
    """Canonicalize internal narration IDs without changing HTML page references.

    Keep the first occurrence of every valid ID, including IDs later in the
    lesson. This keeps cached artifacts stable and prevents repairs from taking
    an ID already assigned to another paragraph. Raw provider output is untouched.
    """
    result = lesson.model_copy(deep=True)
    reserved = {b.id for b in result.blocks if BLOCK_ID.fullmatch(b.id)}
    used = set()
    changes = []
    for index, block in enumerate(result.blocks, 1):
        original = block.id
        if BLOCK_ID.fullmatch(original) and original not in used:
            used.add(original)
            continue
        base = re.sub(r"[^a-z0-9_]+", "_", original.lower()).strip("_")
        if not base:
            base = f"block_{index}"
        if not base[0].isalpha():
            base = "b_" + base
        base = base[:41]
        candidate = base
        suffix = 2
        while candidate in reserved or candidate in used:
            tail = f"_{suffix}"
            candidate = base[: 41 - len(tail)] + tail
            suffix += 1
        block.id = candidate
        used.add(candidate)
        changes.append(
            {
                "position": index,
                "old_id": original,
                "new_id": candidate,
                "slide_id": block.slide_id,
            }
        )
    return result, changes


def validate_lesson(lesson, existing=None):
    if not 2 <= len(lesson.blocks) <= 40:
        raise ValueError("讲稿需要 2 至 40 个自然段")
    ids = set()
    slides = set()
    for b in lesson.blocks:
        if not BLOCK_ID.fullmatch(b.id) or b.id in ids:
            raise ValueError("段落 id 不合法或重复")
        if not b.slide_id or b.slide_id in slides:
            raise ValueError("每个自然段需要独立且唯一的页面 id")
        if len(b.narration) < 15 or len(b.narration) > 1000:
            raise ValueError("口播自然段过短或过长")
        if "[[" in b.narration:
            raise ValueError("口播不能包含保留的画面标记")
        ids.add(b.id)
        slides.add(b.slide_id)
    if existing and [x.slide_id for x in lesson.blocks] != [
        x["id"] for x in existing["slides"]
    ]:
        raise ValueError("讲稿页序与已有课件不一致")


def validate_generated_html(raw, lesson):
    if not raw.strip().lower().startswith(("<!doctype", "<html")):
        raise ValueError("模型未生成完整 HTML")
    if any(
        re.search(pattern, raw, re.IGNORECASE)
        for pattern in [
            r"<iframe",
            r"<form",
            r"\bfetch\s*\(",
            r"XMLHttpRequest",
            r"<(?:script|link|img|audio|video|source|object|embed)\b[^>]*(?:src|href|data)\s*=\s*[\"\'](?:https?:)?//",
            r"url\(\s*[\"\']?(?:https?:)?//",
        ]
    ):
        raise ValueError("自动生成课件必须离线且不包含网络请求")
    if "setPresentationState" not in raw:
        raise ValueError("课件缺少 setPresentationState 接口")
    for b in lesson.blocks:
        if not re.search(r"\bid\s*=\s*[\"\']" + re.escape(b.slide_id) + r"[\"\']", raw):
            raise ValueError("课件缺少页面 " + b.slide_id)


def existing_deck(info, target):
    raw = bundle_html(Path(info["path"]), target)
    if not info["custom"] and not info["reveal"]:
        # Static section decks get a small adapter on the private copy only.
        adapter = """<script>window.setPresentationState=s=>{let pages=[...document.querySelectorAll('section')].filter(e=>!e.parentElement.closest('section'));pages.forEach((e,i)=>{e.style.display=((e.id||e.dataset.slideId||'slide_'+(i+1))===s.slide)?'block':'none'});};</script>"""
        target.write_text(raw + adapter, encoding="utf-8")
    states = {}
    for slide in info["slides"]:
        states[slide["id"]] = (
            {"h": slide["index"], "v": 0, "f": slide.get("fragments", 0) - 1}
            if info["reveal"] and not info["custom"]
            else {"slide": slide["id"], "visible": slide["visible"], "highlight": None}
        )
    return states
