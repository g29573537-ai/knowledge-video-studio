"""Local Kokoro-82M voice provider with preset voices."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import soundfile as sf
from narration_video.core import digest, file_hash, read_json, write_json


class KokoroVoice:
    def __init__(self, config: dict):
        self.config = config
        self.voice = config.get("kokoro_voice", config.get("voice", "af_heart"))
        self.speed = float(config.get("speed", 1.0))
        self.lang_code = config.get("language", "a")
        if self.lang_code not in {"a", "b", "e", "f", "h", "i", "j", "p", "z"}:
            self.lang_code = "a"
        self._pipeline = None

    def identity(self):
        return {"mode": "kokoro", "voice": self.voice, "speed": self.speed}

    def wait_ready(self):
        return None

    def synthesize(self, text: str, cache: Path, identity: dict) -> tuple[Path, bool]:
        cache = Path(cache)
        cache.mkdir(parents=True, exist_ok=True)
        fingerprint = digest(
            {
                "schema": 1,
                "engine": "kokoro",
                "text": text,
                "voice": self.voice,
                "speed": self.speed,
                "lang_code": self.lang_code,
                "identity": identity,
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

        import torch
        from kokoro import KPipeline

        if self._pipeline is None:
            self._pipeline = KPipeline(lang_code=self.lang_code)

        chunks = []
        for _, _, chunk in self._pipeline(text, voice=self.voice, speed=self.speed):
            chunks.append(chunk)
        if not chunks:
            raise RuntimeError("Kokoro returned no audio")
        full = torch.cat(chunks) if len(chunks) > 1 else chunks[0]
        arr = full.detach().cpu().numpy() if hasattr(full, "detach") else full
        if arr.ndim > 1:
            arr = arr.squeeze()
        sf.write(audio, arr, 24000)
        write_json(
            metadata,
            {
                "request": {"engine": "kokoro", "voice": self.voice, "speed": self.speed, "input": text},
                "identity": identity,
                "audio_sha256": file_hash(audio),
                "duration": len(arr) / 24000,
            },
        )
        return audio, False
