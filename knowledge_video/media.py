"""Heavy audio work runs in a child process, isolated from the web server."""

import argparse
from datetime import datetime
import shutil
from pathlib import Path

from narration_video.alignment import align_blocks
from narration_video.cli import execute, synthesize
from narration_video.core import (
    digest,
    file_hash,
    load_project,
    normalized,
    read_json,
    write_json,
)
from narration_video.timeline import compile_timeline


def prepare_reference(source, target):
    import subprocess

    import numpy as np
    import soundfile as sf

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / "decoded.wav"
    out = target / "reference.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            source,
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_f32le",
            str(tmp),
        ],
        check=True,
    )
    audio, sr = sf.read(tmp)
    duration = len(audio) / sr
    if not 3 <= duration <= 60:
        raise ValueError("参考录音需要 3 至 60 秒")
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio * audio)))
    if rms < 0.001:
        raise ValueError("参考录音音量过低或为空")
    sf.write(out, audio * min(1, 0.708 / max(peak, 0.001)), sr, subtype="PCM_16")
    write_json(
        target / "reference_qa.json",
        {"duration": duration, "decoded_peak": peak, "rms": rms},
    )
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["reference", "produce", "transcribe"])
    parser.add_argument("path")
    parser.add_argument("--output")
    parser.add_argument("--repairs", type=int, default=2)
    parser.add_argument("--language", default="auto")
    parser.add_argument(
        "--asr-model", choices=["small", "medium", "large-v3"], default="small"
    )
    args = parser.parse_args()
    if args.stage == "reference":
        p = prepare_reference(args.path, args.output)
        from faster_whisper import WhisperModel

        model = WhisperModel(
            args.asr_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        segs, _ = model.transcribe(
            str(p),
            language=None if args.language == "auto" else args.language,
            beam_size=5,
            vad_filter=False,
        )
        text = "".join(s.text for s in segs).strip()
        if len(normalized(text)) < 4:
            raise ValueError("无法识别有效参考声音，请填写准确逐字稿")
        (p.parent / "reference.txt").write_text(text, encoding="utf-8")
        return
    cfg = load_project(Path(args.path))
    if args.stage == "transcribe":
        from faster_whisper import WhisperModel

        model = WhisperModel(
            cfg.get("asr_model", "small"),
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        manifest = read_json(cfg["build"] / "narration_manifest.json")
        cache = cfg["build"] / "asr_cache"
        cache.mkdir(exist_ok=True)
        rows = []
        for block in manifest["blocks"]:
            target = cache / (
                digest(
                    {
                        "audio": file_hash(Path(block["audio"])),
                        "language": cfg["voice"].get("language", "zh"),
                        "model": cfg.get("asr_model", "small"),
                    }
                )
                + ".json"
            )
            if target.exists():
                actual = read_json(target)["text"]
            else:
                segments, _ = model.transcribe(
                    block["audio"],
                    language=cfg["voice"].get("language", "zh"),
                    beam_size=5,
                    vad_filter=False,
                )
                actual = "".join(s.text for s in segments)
                write_json(target, {"text": actual})
            rows.append(
                {
                    "id": block["id"],
                    "expected": block["text"],
                    "transcribed": actual,
                    "audio_sha256": file_hash(Path(block["audio"])),
                }
            )
        write_json(cfg["build"] / "speech_asr.json", rows)
        return
    attempts = {}
    synthesize(cfg)
    # Audit each natural paragraph. Retry only failed audio; never relax coverage gates.
    while True:
        manifest = read_json(cfg["build"] / "narration_manifest.json")
        source_cfg = {**cfg, "duration": manifest["source_duration"]}
        failures = []
        for block in manifest["blocks"]:
            try:
                aligned = align_blocks([block], source_cfg)
                compile_timeline(aligned, cfg["cues"], source_cfg)
            except ValueError as exc:
                failures.append((block, str(exc)))
        if not failures:
            break
        for block, error in failures:
            attempt = attempts.get(block["id"], 0) + 1
            attempts[block["id"]] = attempt
            print(f"[{datetime.now().isoformat(timespec='seconds')}] REPAIR {block['id']} {attempt}/{args.repairs}: {error}", flush=True)
            if attempt > args.repairs:
                raise RuntimeError(
                    f"段落 {block['id']} 在 {args.repairs} 次重做后仍未通过：{error}"
                )
            rejected = cfg["build"] / "rejected" / block["id"] / str(attempt)
            rejected.mkdir(parents=True, exist_ok=True)
            for metadata in (cfg["build"] / "voice_cache").glob("*.json"):
                if read_json(metadata)["request"]["input"] == block["text"]:
                    for f in [metadata, metadata.with_suffix(".wav")]:
                        if f.exists():
                            shutil.move(f, rejected / f.name)
        synthesize(cfg)
    execute(cfg, "align")
    execute(cfg, "render")


if __name__ == "__main__":
    main()
