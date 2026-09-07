"""Run both local services and stop only processes launched by this command."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def occupied(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--voice-port", type=int, default=3900)
    args = parser.parse_args()
    if occupied(args.port):
        raise SystemExit(
            f"Port {args.port} is occupied; existing service was left running."
        )
    omni = Path(os.environ.get("OMNIVOICE_STUDIO_ROOT", ROOT / ".runtime/omnivoice"))
    processes = []
    env = {
        **os.environ,
        "OMNIVOICE_MODEL_LOAD_TIMEOUT": "3600",
        "OMNIVOICE_IDLE_TIMEOUT_S": "3600",
        "STUDIO_VOICE_URL": f"http://127.0.0.1:{args.voice_port}",
    }

    # OmniVoice may preload cached weights; first-time downloads are also available in the UI.
    def stop(*unused):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, stop)
    try:
        if not occupied(args.voice_port):
            processes.append(
                subprocess.Popen(
                    [
                        str(omni / ".venv/bin/python"),
                        "-m",
                        "uvicorn",
                        "backend.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.voice_port),
                    ],
                    cwd=omni,
                    env=env,
                    start_new_session=True,
                )
            )
        else:
            print(
                f"Reusing voice service on port {args.voice_port}; it will not be stopped by this launcher."
            )
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "knowledge_video.cli",
                    "serve",
                    "--port",
                    str(args.port),
                ],
                cwd=ROOT,
                env=env,
                start_new_session=True,
            )
        )
        print(
            f"Open http://127.0.0.1:{args.port}/ (voice service http://127.0.0.1:{args.voice_port})",
            flush=True,
        )
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in processes:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()


if __name__ == "__main__":
    main()
