from __future__ import annotations

import math
import os
from pathlib import Path

from .core import digest, file_hash, normalized, read_json, write_json


def validate_alignment_runs(chars):
    # Overall coverage can hide a completely omitted phrase in a long paragraph.
    run = 0
    for char in chars:
        run = 0 if char["valid"] else run + 1
        if run > 3:
            raise ValueError(
                "Consecutive unaligned characters suggest an omitted phrase; review/re-record narration"
            )


def extract_chars(
    result: dict, text: str, duration: float, min_score=0.1, min_coverage=0.9
):
    chars = []
    for seg in result["segments"]:
        for item in seg.get("chars", []):
            char = normalized(item.get("char", ""))
            if not char:
                continue
            if len(char) != 1:
                raise ValueError("Alignment returned a non-character token")
            start, end, score = item.get("start"), item.get("end"), item.get("score")
            valid = all(
                isinstance(v, (int, float)) and math.isfinite(v)
                for v in [start, end, score]
            )
            valid = valid and 0 <= start < end <= duration + 0.05 and score >= min_score
            chars.append(
                {
                    "char": char,
                    "start": start,
                    "end": end,
                    "score": score,
                    "valid": bool(valid),
                }
            )
    if "".join(c["char"] for c in chars) != normalized(text):
        raise ValueError(
            "Forced alignment does not cover the exact spoken script; refusing estimated timing"
        )
    coverage = sum(c["valid"] for c in chars) / max(len(chars), 1)
    if coverage < min_coverage:
        raise ValueError(
            f"Alignment coverage {coverage:.1%} < {min_coverage:.1%}; review/re-record narration"
        )
    validate_alignment_runs(chars)
    previous = -1.0
    for c in chars:
        if c["valid"]:
            if c["start"] < previous - 0.025:
                raise ValueError("Non-monotonic alignment")
            previous = c["start"]
    return {"chars": chars, "coverage": coverage}


def align_blocks(blocks: list[dict], cfg: dict):
    """Only force-align the known script. No ASR rewrite or duration interpolation."""
    # Do not launch Transformers' unsolicited remote conversion/background thread.
    os.environ["DISABLE_SAFETENSORS_CONVERSION"] = "1"
    import importlib.metadata

    import soundfile as sf
    import torch
    from whisperx.alignment import align, load_align_model
    from whisperx.audio import load_audio

    options = cfg.get("alignment", {})
    language = options.get("language", "zh")
    device = options.get("device", "cpu")
    torch.set_num_threads(int(options.get("threads", 4)))
    model = metadata = None
    cache = cfg["build"] / "alignment"
    results = []
    for block in blocks:
        path = Path(block["audio"])
        duration = sf.info(path).duration
        key = digest(
            {
                "audio": file_hash(path),
                "text": block["text"],
                "options": options,
                "whisperx": importlib.metadata.version("whisperx"),
                "schema": 1,
            }
        )
        target = cache / f"{key}.json"
        if target.exists():
            aligned = read_json(target)
            validate_alignment_runs(aligned["chars"])
            print(f"ALIGN cache {block['id']}", flush=True)
        else:
            if model is None:
                print(
                    f"ALIGN loading {language} acoustic model on {device}", flush=True
                )
                model, metadata = load_align_model(
                    language, device, model_name=options.get("model")
                )
            print(f"ALIGN {block['id']} ({duration:.2f}s)", flush=True)
            raw = align(
                [{"start": 0.0, "end": duration, "text": block["text"]}],
                model,
                metadata,
                load_audio(str(path)),
                device,
                return_char_alignments=True,
            )
            # Preserve raw acoustic evidence even when validation fails.
            write_json(cache / f"{key}.raw.json", raw)
            aligned = extract_chars(
                raw,
                block["text"],
                duration,
                options.get("min_char_score", 0.1),
                options.get("min_coverage", 0.9),
            )
            write_json(target, aligned)
        results.append({**block, **aligned, "duration": duration})
    return results
