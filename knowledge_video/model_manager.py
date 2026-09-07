"""One bounded model preparation process with persistent download receipts."""

import concurrent.futures
import json
import os
import sys
import threading
from pathlib import Path

from .languages import LANGUAGES, ASR_MODELS
from .runtime import run_process


class ModelManager:
    def __init__(self, data):
        self.root = Path(data) / "models"
        self.root.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.state = {
            "status": "idle",
            "message": "选择语言后下载或加载模型",
            "step": 0,
            "steps": 4,
        }

    def catalog(self):
        receipts = []
        for file in self.root.glob("*.json"):
            try:
                d = json.loads(file.read_text())
                valid = bool(d.get("files")) and all(
                    Path(f["path"]).is_file()
                    and Path(f["path"]).stat().st_size == f["size"]
                    for f in d["files"]
                )
                if valid:
                    receipts.append(
                        {"language": d["language"], "asr_model": d["asr_model"]}
                    )
            except (ValueError, OSError, KeyError, TypeError):
                continue
        with self.lock:
            state = dict(self.state)
        return {
            "languages": LANGUAGES,
            "asr_models": ASR_MODELS,
            "tts_model": "k2-fsa/OmniVoice",
            "prepared": receipts,
            "operation": state,
        }

    def start(self, language, asr_model, action, voice_url):
        if (
            language not in LANGUAGES
            or asr_model not in ASR_MODELS
            or action not in ("download", "load")
        ):
            raise ValueError("Unsupported language, model or action")
        with self.lock:
            if self.state["status"] == "running":
                raise ValueError("已有模型准备任务正在运行")
            self.state = {
                "status": "running",
                "message": "开始准备模型，已有下载会复用",
                "step": 0,
                "steps": 4,
                "language": language,
                "asr_model": asr_model,
                "action": action,
            }
        self.pool.submit(self._run, language, asr_model, action, voice_url)
        return dict(self.state)

    def _run(self, language, asr_model, action, voice_url):
        output = self.root / f"{language}-{asr_model}.json"

        def log(line):
            if line.startswith("STEP "):
                step = int(line.split()[1].split("/")[0])
                with self.lock:
                    self.state.update(step=step, message=line.split(" ", 2)[2])

        try:
            env = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent)
                + os.pathsep
                + os.environ.get("PYTHONPATH", ""),
            }
            run_process(
                [
                    sys.executable,
                    "-m",
                    "knowledge_video.model_worker",
                    "--language",
                    language,
                    "--asr-model",
                    asr_model,
                    "--action",
                    action,
                    "--voice-url",
                    voice_url,
                    "--output",
                    output,
                ],
                self.root,
                threading.Event(),
                7200,
                log=log,
                env=env,
            )
            with self.lock:
                self.state.update(
                    status="completed",
                    step=4,
                    message="模型已载入，可以制作视频"
                    if action == "load"
                    else "模型已下载，可点击载入",
                )
        except Exception as exc:
            with self.lock:
                self.state.update(status="failed", message=str(exc)[-1200:])
