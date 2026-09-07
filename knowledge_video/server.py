from __future__ import annotations

import importlib.util
import json
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from narration_video.voice import OmniVoice

from .jobs import Jobs
from .materials import bundle_html, inspect_slides
from .models import JobRequest

PUBLIC = {
    "build/video.mp4",
    "build/narration.wav",
    "build/subtitles.srt",
    "script.md",
    "description.md",
    "chapters.json",
    "quality.json",
    "slides.html",
}


def create_app(data_dir=None):
    data = (
        Path(data_dir or os.environ.get("STUDIO_DATA_DIR", ".studio"))
        .expanduser()
        .resolve()
    )
    data.mkdir(parents=True, exist_ok=True)
    jobs = Jobs(data)
    app = FastAPI(title="Knowledge Video Studio")
    app.state.jobs = jobs

    @app.middleware("http")
    async def local_only(request, call_next):
        # Bind loopback and reject cross-origin mutations / DNS rebinding.
        host = request.url.hostname
        if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return __import__(
                "starlette.responses", fromlist=["JSONResponse"]
            ).JSONResponse({"detail": "仅支持本机访问"}, 403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return __import__(
                "starlette.responses", fromlist=["JSONResponse"]
            ).JSONResponse({"detail": "拒绝跨站请求"}, 403)
        if request.method == "POST" and request.headers.get("x-studio-client") != "1":
            return __import__(
                "starlette.responses", fromlist=["JSONResponse"]
            ).JSONResponse({"detail": "缺少本机客户端标识"}, 403)
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return __import__(
            "starlette.responses", fromlist=["JSONResponse"]
        ).JSONResponse({"detail": "任务不存在"}, 404)

    @app.get("/api/system")
    def system():
        from .providers import codex_binary
        from .workflow import chrome_path

        result = {
            "codex": codex_binary(),
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "node": shutil.which("node"),
            "chrome": chrome_path(),
            "media_installed": bool(importlib.util.find_spec("whisperx")),
            "data_dir": str(data),
        }
        try:
            result["voice"] = OmniVoice({}).json("/model/status")
        except Exception:
            result["voice"] = {
                "loaded": False,
                "detail": "请启动 OmniVoice Studio 服务",
            }
        return result

    @app.get("/api/template/default")
    def default_template():
        return FileResponse(Path(__file__).parent / "templates/default.html")

    @app.get("/api/templates")
    def templates():
        result = []
        for manifest in sorted((data / "templates").glob("*/template.json")):
            try:
                entry = json.loads(manifest.read_text())
                path = (manifest.parent / entry["file"]).resolve()
                if (
                    not path.is_relative_to(manifest.parent.resolve())
                    or not path.is_file()
                ):
                    continue
                result.append(
                    {
                        "id": "local-" + manifest.parent.name,
                        "name": str(entry["name"]),
                        "description": str(entry.get("description", "本机模板")),
                        "path": str(path),
                    }
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return result + [
            {
                "id": "default",
                "name": "通用教学",
                "description": "黑底 · 蓝色强调 · 简洁排版",
                "path": "",
            }
        ]

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.list()

    @app.get("/api/jobs/{id}")
    def get_job(id: str):
        return jobs.get(id)

    @app.post("/api/jobs")
    def create_job(request: JobRequest):
        if request.voice_upload:
            if not request.voice_upload.isalnum():
                raise HTTPException(400, "上传编号不合法")
            upload = data / "uploads" / request.voice_upload / "audio"
            if not upload.exists():
                raise HTTPException(400, "录音上传已失效")
            request.voice_path = str(upload)
        if (
            not request.profile_id
            and not Path(request.voice_path).expanduser().is_file()
        ):
            raise HTTPException(400, "请上传参考录音或选择已有声音档案")
        try:
            if request.slides_mode == "existing":
                inspect_slides(request.slides_path)
            elif request.template_path:
                inspect_slides(request.template_path)
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))
        try:
            return jobs.create(request)
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/jobs/{id}/cancel")
    def cancel(id: str):
        try:
            return jobs.cancel(id)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/jobs/{id}/resume")
    def resume(id: str, body: dict):
        try:
            jobs.start(id, body.get("api_key"))
            return jobs.get(id)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/upload")
    async def upload(file: UploadFile):
        if Path(file.filename or "").suffix.lower() not in (
            ".wav",
            ".m4a",
            ".mp3",
            ".flac",
            ".ogg",
            ".aac",
        ):
            raise HTTPException(400, "不支持此音频格式")
        id = uuid.uuid4().hex
        folder = data / "uploads" / id
        folder.mkdir(parents=True)
        size = 0
        try:
            with (folder / "audio").open("wb") as output:
                while chunk := await file.read(65536):
                    size += len(chunk)
                    if size > 30_000_000:
                        raise HTTPException(413, "录音不能超过 30 MB")
                    output.write(chunk)
        except Exception:
            shutil.rmtree(folder)
            raise
        return {"id": id, "name": file.filename, "size": size}

    @app.post("/api/slides/inspect")
    def slides(body: dict):
        try:
            info = inspect_slides(body.get("path", ""))
            id = uuid.uuid4().hex
            folder = data / "previews" / id
            folder.mkdir(parents=True)
            bundle_html(Path(info["path"]), folder / "slides.html")
            return {
                "slides": info["slides"],
                "custom": info["custom"],
                "reveal": info["reveal"],
                "preview": "/previews/" + id + "/slides.html",
            }
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))

    @app.get("/api/profiles")
    def profiles(url: str = "http://127.0.0.1:3900"):
        try:
            return OmniVoice({"base_url": url}).json("/profiles")
        except Exception as e:
            raise HTTPException(502, str(e))

    @app.get("/artifacts/{id}/{name:path}")
    def artifact(id: str, name: str):
        base = jobs.path(id)
        path = (base / name).resolve()
        allowed = name in PUBLIC or name.startswith(("assets/", "build/slides/"))
        if not allowed or not path.is_relative_to(base) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    (data / "previews").mkdir(exist_ok=True)
    app.mount("/previews", StaticFiles(directory=data / "previews"), name="previews")
    app.mount(
        "/",
        StaticFiles(directory=Path(__file__).parent / "static", html=True),
        name="frontend",
    )
    return app
