from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path


class Cancelled(RuntimeError):
    pass


def run_process(args, cwd, cancel=None, timeout=900, stdin=None, log=None, env=None):
    """No shell interpolation. Cancel the entire owned process group."""
    proc = subprocess.Popen(
        [str(x) for x in args],
        cwd=cwd,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        start_new_session=os.name != "nt",
    )
    lines = []

    def drain():
        for line in proc.stdout:
            lines.append(line)
            if log:
                log(line.rstrip())

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    if stdin is not None:
        try:
            proc.stdin.write(stdin)
            proc.stdin.close()
        except BrokenPipeError:
            pass
    start = time.monotonic()
    try:
        while proc.poll() is None:
            if cancel and cancel.is_set():
                raise Cancelled("任务已取消")
            if time.monotonic() - start > timeout:
                raise TimeoutError("子进程超过时限")
            time.sleep(0.15)
    except BaseException:
        if proc.poll() is None:
            if os.name == "nt":
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
        raise
    finally:
        reader.join(timeout=3)
    output = "".join(lines)
    if proc.returncode:
        raise RuntimeError(output[-5000:] or f"Process exited {proc.returncode}")
    return output


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
