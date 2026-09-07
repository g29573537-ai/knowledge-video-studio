import argparse
import json
import os
import sys
import threading
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Knowledge Video Studio")
    sub = parser.add_subparsers(dest="command", required=True)
    web = sub.add_parser("serve")
    web.add_argument("--port", type=int, default=8770)
    web.add_argument("--data", default=os.environ.get("STUDIO_DATA_DIR", ".studio"))
    run = sub.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output", type=Path, required=True)
    sub.add_parser("doctor")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        from .server import create_app

        uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port)
    elif args.command == "doctor":
        import importlib.util
        import shutil

        from .workflow import chrome_path

        print(
            json.dumps(
                {
                    "python": sys.version,
                    "codex": shutil.which("codex"),
                    "node": shutil.which("node"),
                    "ffmpeg": shutil.which("ffmpeg"),
                    "chrome": chrome_path(),
                    "whisperx": bool(importlib.util.find_spec("whisperx")),
                },
                indent=2,
            )
        )
    else:
        from .models import JobRequest
        from .workflow import Workflow

        args.output.mkdir(parents=True, exist_ok=True)
        r = JobRequest.model_validate_json(args.request.read_text())
        result = Workflow(
            args.output.resolve(),
            r,
            lambda message, **kw: print(message, flush=True),
            threading.Event(),
        ).run()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
