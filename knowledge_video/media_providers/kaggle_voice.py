"""Kaggle-backed voice provider.

This is an independent adapter for running CosyVoice3 (or another TTS engine) on a
Kaggle kernel.  It follows the same synthesize/cache contract as
``narration_video.voice.OmniVoice`` so it can be selected explicitly without
changing the rest of the narration pipeline.

The provider never treats a missing Kaggle credential or a non-terminal kernel
status as success.  Polling exits as soon as Kaggle reports a terminal status.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from narration_video.core import digest, file_hash, read_json, write_json


TERMINAL_FAILURES = {"error", "failed", "cancelled", "timeout"}


def _kaggle_cmd(config: dict[str, Any]) -> str:
    return str(config.get("kaggle_cmd") or os.environ.get("KAGGLE_CMD") or "kaggle")


def _parse_status(text: str) -> str:
    match = re.search(r"KernelWorkerStatus\.([A-Za-z_]+)", text)
    token = match.group(1) if match else text.strip()
    return token.lower()


class KaggleVoice:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.kaggle_cmd = _kaggle_cmd(config)
        self.kernel_slug = str(config.get("kernel_slug") or "").strip()
        self.timeout = int(config.get("timeout_seconds", config.get("timeout", 3600)))
        self.total_timeout = int(config.get("total_timeout", 3600))
        self.poll_backoff = float(config.get("poll_backoff", 15.0))
        self.enable_gpu = bool(config.get("enable_gpu", True))
        self.enable_internet = bool(config.get("enable_internet", True))
        self.run_py = config.get("run_py")

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            check=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

    def _push(self, job_folder: Path) -> None:
        cmd = [
            self.kaggle_cmd,
            "kernels",
            "push",
            "-p",
            str(job_folder),
            "-t",
            str(self.timeout),
            "--accelerator",
            "NvidiaTeslaT4" if self.enable_gpu else "none",
        ]
        # The installed Kaggle CLI spelling for internet may vary; keep the push
        # minimal and rely on kernel-metadata.json for the rest.
        self._run(cmd, self.timeout + 60)

    def _poll(self, kernel_slug: str) -> None:
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= self.total_timeout:
                raise RuntimeError("Kaggle voice kernel did not finish before total timeout")
            try:
                result = self._run(
                    [self.kaggle_cmd, "kernels", "status", kernel_slug],
                    timeout=60,
                )
                status = _parse_status(result.stdout or "")
            except (subprocess.SubprocessError, OSError):
                time.sleep(min(self.poll_backoff, self.total_timeout - elapsed))
                continue

            if status == "complete":
                return
            if status in TERMINAL_FAILURES:
                raise RuntimeError(f"Kaggle voice kernel reached terminal status: {status}")
            remaining = self.total_timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise RuntimeError("Kaggle voice kernel did not finish before total timeout")
            time.sleep(min(self.poll_backoff, remaining))

    def _fetch_output(self, kernel_slug: str, dest: Path) -> list[Path]:
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            [self.kaggle_cmd, "kernels", "output", kernel_slug, "-p", str(dest), "-q"],
            timeout=300,
        )
        files = [p for p in dest.iterdir() if p.is_file()]
        if not files:
            raise RuntimeError("Kaggle voice kernel returned no output files")
        return files

    def synthesize(self, text: str, cache: Path, identity: dict[str, Any]) -> tuple[Path, bool]:
        cache = Path(cache)
        cache.mkdir(parents=True, exist_ok=True)
        fingerprint = digest(
            {
                "schema": 1,
                "engine": "kaggle_cosyvoice3",
                "text": text,
                "identity": identity,
                "kernel_slug": self.kernel_slug,
            }
        )
        audio = cache / f"{fingerprint}.wav"
        metadata = cache / f"{fingerprint}.json"
        if audio.exists() and metadata.exists():
            try:
                info = read_json(metadata)
            except (OSError, json.JSONDecodeError):
                info = {}
            if info.get("audio_sha256") == file_hash(audio):
                return audio, True

        if not self.kernel_slug:
            raise ValueError("Kaggle voice requires kernel_slug")
        if not self.run_py:
            raise ValueError("Kaggle voice requires run_py for the CosyVoice kernel")

        job_id = f"kvoice_{fingerprint[:12]}"
        job_folder = cache / f"kaggle_job_{fingerprint}"
        job_folder.mkdir(parents=True, exist_ok=True)
        (job_folder / "job.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "text": text,
                    "engine": "cosyvoice3",
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (job_folder / "run.py").write_text(str(self.run_py), encoding="utf-8")
        (job_folder / "kernel-metadata.json").write_text(
            json.dumps(
                {
                    "id": self.kernel_slug,
                    "title": self.kernel_slug.split("/")[-1],
                    "code_file": "run.py",
                    "language": "python",
                    "kernel_type": "script",
                    "is_private": True,
                    "enable_gpu": self.enable_gpu,
                    "enable_internet": self.enable_internet,
                    "dataset_sources": [],
                    "competition_sources": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        self._push(job_folder)
        self._poll(self.kernel_slug)
        output_dir = cache / f"kaggle_output_{fingerprint}"
        files = self._fetch_output(self.kernel_slug, output_dir)
        wav_candidates = [p for p in files if p.suffix.lower() in {".wav", ".mp3", ".flac"}]
        if not wav_candidates:
            raise RuntimeError("Kaggle voice kernel returned no audio file")
        source = wav_candidates[0]
        if source.suffix.lower() != ".wav":
            # Keep the rest of the pipeline on WAV input.
            tmp = audio.with_suffix(".partial.wav")
            self._run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), str(tmp)],
                300,
            )
            tmp.replace(audio)
        else:
            source.replace(audio)

        info = {
            "request": {"engine": "kaggle_cosyvoice3", "kernel_slug": self.kernel_slug},
            "identity": identity,
            "audio_sha256": file_hash(audio),
            "duration": None,
        }
        write_json(metadata, info)
        return audio, False
