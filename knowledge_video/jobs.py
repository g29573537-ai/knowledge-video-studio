from __future__ import annotations

import concurrent.futures
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from .models import JobRequest
from .run_state import RunStore
from .runtime import Cancelled, atomic_json
from .workflow import Workflow


class Jobs:
    def __init__(self, data):
        self.data = Path(data).resolve()
        self.root = self.data / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.lock = threading.RLock()
        self.running = {}
        self.secrets = {}
        for path in self.root.glob("*/status.json"):
            state = json.loads(path.read_text())
            if state.get("publishing", {}).get("status") in ("running", "queued"):
                state["publishing"] = {"status": "interrupted", "message": "服务重启，请重新生成封面与简介"}
                atomic_json(path, state)
            if state["status"] in ("running", "queued"):
                state.update(status="interrupted", message="服务重启中断，可继续任务")
                atomic_json(path, state)

    def path(self, id):
        if len(id) != 32 or any(c not in "0123456789abcdef" for c in id):
            raise KeyError(id)
        path = self.root / id
        if not path.is_dir():
            raise KeyError(id)
        return path

    def get(self, id):
        return json.loads((self.path(id) / "status.json").read_text())

    def list(self):
        return sorted(
            [json.loads(x.read_text()) for x in self.root.glob("*/status.json")],
            key=lambda x: x["created"],
            reverse=True,
        )[:50]

    def create(self, request):
        id = uuid.uuid4().hex
        p = self.root / id
        p.mkdir()
        if not request.profile_id:
            source = Path(request.voice_path).expanduser()
            private = p / "input"
            private.mkdir()
            if source.stat().st_size > 30_000_000:
                raise ValueError("录音不能超过 30 MB")
            recording = private / "recording"
            shutil.copy2(source, recording)
            request = request.model_copy(update={"voice_path": str(recording)})
        public = request.model_dump()
        public["provider"]["api_key"] = ""
        atomic_json(p / "request.json", public)
        self.secrets[id] = request.provider.api_key
        atomic_json(
            p / "status.json",
            {
                "id": id,
                "topic": request.topic,
                "created": time.time(),
                "status": "queued",
                "stage": "queued",
                "message": "等待开始",
                "events": [],
            },
        )
        self.start(id)
        return self.get(id)

    def start(self, id, key=None):
        with self.lock:
            if id in self.running:
                raise ValueError("任务已在运行")
            state = self.get(id)
            if state["status"] == "completed":
                raise ValueError("任务已完成，请新建任务修改参数")
            request = JobRequest.model_validate_json(
                (self.path(id) / "request.json").read_text()
            )
            request.provider.api_key = key or self.secrets.get(id, "")
            if key:
                self.secrets[id] = key
            cancel = threading.Event()
            self.running[id] = cancel
            state.update(status="queued", message="等待开始")
            atomic_json(self.path(id) / "status.json", state)
            self.pool.submit(self._run, id, request, cancel)

    def cancel(self, id):
        with self.lock:
            if id not in self.running:
                raise ValueError("任务当前未运行")
            self.running[id].set()
        return {"ok": True}

    def publish_assets(self, id, key=None):
        with self.lock:
            state = self.get(id)
            if state["status"] != "completed":
                raise ValueError("请先完成视频制作")
            if id in self.running:
                raise ValueError("封面与简介正在生成")
            request = JobRequest.model_validate_json((self.path(id) / "request.json").read_text())
            request.provider.api_key = key or self.secrets.get(id, "")
            if key:
                self.secrets[id] = key
            cancel = threading.Event()
            self.running[id] = cancel
            state["publishing"] = {"status": "queued", "message": "等待生成封面与简介"}
            atomic_json(self.path(id) / "status.json", state)
            self.pool.submit(self._publish_assets, id, request, cancel)
            return state

    def _publish_assets(self, id, request, cancel):
        def update(message, **extra):
            with self.lock:
                state = self.get(id)
                state["publishing"] = {"status": "running", "message": str(message)[-1000:], **extra}
                atomic_json(self.path(id) / "status.json", state)
        try:
            update("生成封面与简介")
            result = Workflow(self.path(id), request, update, cancel).make_publication()
            with self.lock:
                state = self.get(id)
                state.update(publication=result, publishing={"status": "completed", "message": "封面与简介已生成"})
                atomic_json(self.path(id) / "status.json", state)
        except Exception as exc:
            update(str(exc), status="failed")
        finally:
            with self.lock:
                self.running.pop(id, None)

    def _run(self, id, request, cancel):
        p = self.path(id)
        store = RunStore(p)
        try:
            store.start({"request": request.model_dump()})
        except Exception:
            pass

        def update(message, stage=None, **extra):
            with self.lock:
                state = self.get(id)
                if stage:
                    state["stage"] = stage
                state.update(extra)
                state["message"] = str(message)[-1500:]
                state["updated"] = time.time()
                state["events"] = (
                    state.get("events", [])
                    + [
                        {
                            "time": time.time(),
                            "stage": state["stage"],
                            "text": str(message)[-1500:],
                        }
                    ]
                )[-250:]
                atomic_json(p / "status.json", state)
                try:
                    RunStore(p).heartbeat(state.get("stage"))
                except Exception:
                    pass

        try:
            update("任务开始", status="running")
            result = Workflow(p, request, update, cancel).run()
            if cancel.is_set():
                raise Cancelled("任务已取消")
            update("视频已完成", stage="completed", status="completed", result=result)
            try:
                RunStore(p).complete()
            except Exception:
                pass
        except Cancelled:
            update("任务已取消，可继续", status="cancelled")
        except Exception as e:
            update(str(e), status="failed")
        finally:
            with self.lock:
                self.running.pop(id, None)
