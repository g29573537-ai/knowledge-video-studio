from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .core import digest, file_hash, probe, read_json, write_json


class OmniVoice:
    def __init__(self, config: dict):
        self.config = config
        self.base = config.get("base_url", "http://127.0.0.1:3900").rstrip("/")
        self.timeout = float(config.get("timeout_seconds", 900))

    def request(self, route, data=None, content_type="application/json", timeout=None):
        headers = {"Accept": "application/json"}
        key_env = self.config.get("api_key_env", "OMNIVOICE_API_KEY")
        if os.environ.get(key_env):
            headers["Authorization"] = "Bearer " + os.environ[key_env]
        if data is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.base + route, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            detail = e.read(2000).decode(errors="replace")
            raise RuntimeError(f"OmniVoice {route}: HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise RuntimeError(
                f"OmniVoice {route} unavailable or timed out: {e}"
            ) from e

    def json(self, route):
        return json.loads(self.request(route, timeout=20))

    def wait_ready(self):
        # This OmniVoice checkout submits cold model loads into the inference pool.
        # Warm up through the async setup endpoint before entering inference.
        if self.config.get("model", "omnivoice") != "omnivoice":
            return
        deadline = time.monotonic() + float(
            self.config.get("warmup_timeout_seconds", 900)
        )
        previous = None
        warmup_requested = False
        while True:
            status = self.json("/model/status")
            if status.get("loaded"):
                return
            if status.get("error"):
                raise RuntimeError(f"OmniVoice 模型加载失败：{status['error']}")
            if not status.get("loading") and not warmup_requested:
                try:
                    self.request("/setup/warmup", data=b"{}", timeout=20)
                except RuntimeError as exc:
                    raise RuntimeError(
                        "OmniVoice 模型未加载，自动唤醒失败。请在语音服务中加载模型后继续任务。"
                    ) from exc
                warmup_requested = True
                print("VOICE waking idle model; waiting for loaded=true", flush=True)
            detail = status.get("detail", status.get("status"))
            if detail != previous:
                print(f"VOICE waiting for model: {detail}", flush=True)
                previous = detail
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "OmniVoice 模型唤醒超时，尚未确认 loaded=true；请检查语音服务日志后继续任务"
                )
            time.sleep(3)

    def identity(self):
        """Do not let OmniVoice silently map a missing clone profile to its default."""
        mode = self.config.get("mode", "clone")
        profile_id = self.config.get("profile_id")
        if mode == "design":
            return {
                "mode": "synthetic-design",
                "voice_revision": self.config.get("revision", "1"),
            }
        if mode != "clone" or not profile_id or profile_id == "default":
            raise ValueError("Clone mode requires an explicit OmniVoice profile_id")
        profile = self.json(f"/profiles/{profile_id}")
        if not (profile.get("ref_audio_path") or profile.get("locked_audio_path")):
            raise ValueError(f"Profile {profile_id} has no reference audio")
        reference = self.request(f"/profiles/{profile_id}/audio", timeout=30)
        import hashlib

        return {
            "mode": "clone",
            "profile_id": profile_id,
            "reference_sha256": hashlib.sha256(reference).hexdigest(),
            "profile": {
                k: profile.get(k) for k in ["ref_text", "instruct", "seed", "is_locked"]
            },
            "voice_revision": self.config.get("revision", "1"),
        }

    def body(self, text):
        return {
            "model": self.config.get("model", "omnivoice"),
            "voice": self.config.get("profile_id", "default"),
            "input": text,
            "response_format": "wav",
            "language": self.config.get("language", "zh"),
            "speed": self.config.get("speed", 1.0),
            "instruct": self.config.get("instruct"),
            "denoise": True,
        }

    def synthesize(self, text, cache: Path, identity: dict) -> tuple[Path, bool]:
        body = self.body(text)
        fingerprint = digest(
            {"schema": 1, "endpoint": self.base, "request": body, "identity": identity}
        )
        cache.mkdir(parents=True, exist_ok=True)
        audio = cache / f"{fingerprint}.wav"
        metadata = cache / f"{fingerprint}.json"
        if audio.exists() and metadata.exists():
            info = read_json(metadata)
            if info.get("audio_sha256") == file_hash(audio):
                return audio, True
        started = time.monotonic()
        payload = self.request(
            "/v1/audio/speech", json.dumps(body, ensure_ascii=False).encode()
        )
        tmp = audio.with_suffix(".partial.wav")
        try:
            tmp.write_bytes(payload)
            info = probe(tmp)
            if (
                not any(s["codec_type"] == "audio" for s in info["streams"])
                or float(info["format"]["duration"]) <= 0
            ):
                raise ValueError("OmniVoice returned empty/non-audio output")
            tmp.replace(audio)
        finally:
            tmp.unlink(missing_ok=True)
        write_json(
            metadata,
            {
                "request": body,
                "identity": identity,
                "audio_sha256": file_hash(audio),
                "duration": float(info["format"]["duration"]),
                "elapsed_seconds": time.monotonic() - started,
            },
        )
        return audio, False

    def import_voice(self, audio: Path, text: str, name: str):
        boundary = "narration-" + uuid.uuid4().hex
        pieces = []
        for key, value in {
            "name": name,
            "ref_text": text,
            "language": self.config.get("reference_language", "auto"),
            "kind": "clone",
        }.items():
            pieces.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )
        pieces.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="ref_audio"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        )
        pieces.extend([audio.read_bytes(), f"\r\n--{boundary}--\r\n".encode()])
        return json.loads(
            self.request(
                "/profiles",
                b"".join(pieces),
                f"multipart/form-data; boundary={boundary}",
            )
        )
