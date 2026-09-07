from __future__ import annotations

import copy
import math
from pathlib import Path

from .core import probe, run


def retime_audio(source: Path, target: Path, speed: float) -> float:
    """Change tempo without changing pitch; retain the complete source timeline."""
    if not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError("playback_speed must be between 0.5 and 2")
    info = probe(source)
    sr = int(
        next(s for s in info["streams"] if s["codec_type"] == "audio")["sample_rate"]
    )
    samples = round(float(info["format"]["duration"]) * sr / speed)
    tmp = target.with_suffix(".partial.wav")
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                source,
                "-af",
                f"atempo={speed},apad,atrim=end_sample={samples}",
                "-c:a",
                "pcm_s16le",
                tmp,
            ]
        )
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return samples / sr


def retime_timeline(timeline: dict, speed: float, duration: float) -> dict:
    """Map measured source timestamps through the same global tempo change."""
    result = copy.deepcopy(timeline)
    result["source_duration"] = timeline["duration"]
    result["playback_speed"] = speed
    result["duration"] = duration
    for event in result["events"]:
        for key in ("time", "spoken_time"):
            event[key] /= speed
    for caption in result["subtitles"]:
        for key in ("start", "end"):
            caption[key] /= speed
    for block in result["blocks"]:
        for key in ("offset", "duration"):
            block[key] /= speed
    return result
