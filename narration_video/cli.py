from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from .core import (
    digest,
    file_hash,
    load_project,
    read_json,
    run,
    timing_spec,
    write_json,
)
from .voice import OmniVoice


def synthesize(cfg):
    import numpy as np
    import soundfile as sf

    backend = cfg["voice"].get("backend", "omnivoice")
    if backend == "kaggle_cosyvoice3":
        from knowledge_video.media_providers.kaggle_voice import KaggleVoice

        service = KaggleVoice(cfg["voice"])
        identity = service.identity() if hasattr(service, "identity") else {}
        if hasattr(service, "wait_ready"):
            service.wait_ready()
    elif backend == "kokoro":
        from knowledge_video.media_providers.kokoro_voice import KokoroVoice

        service = KokoroVoice(cfg["voice"])
        identity = service.identity()
        service.wait_ready()
    else:
        service = OmniVoice(cfg["voice"])
        identity = service.identity()
        service.wait_ready()
    cache = cfg["build"] / "voice_cache"
    normalized = cfg["build"] / "audio"
    normalized.mkdir(parents=True, exist_ok=True)
    blocks = []
    # Stable hashes allow reordered blocks to reuse their speech without using stale text/voices.
    for i, block in enumerate(cfg["blocks"], 1):
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] VOICE {i}/{len(cfg['blocks'])} {block['id']}",
            flush=True,
        )
        raw, hit = service.synthesize(block["text"], cache, identity)
        audio = normalized / f"{file_hash(raw)}.wav"
        if not audio.exists():
            tmp = audio.with_suffix(".partial.wav")
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    raw,
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    tmp,
                ]
            )
            tmp.replace(audio)
        blocks.append({**block, "audio": str(audio), "cache_hit": hit})
    clock = 0
    pause = round(cfg.get("pause_between_blocks", 0.35) * 24000)
    master = cfg["build"] / "narration.wav"
    temporary = master.with_suffix(".partial.wav")
    with sf.SoundFile(
        temporary, "w", samplerate=24000, channels=1, subtype="PCM_16"
    ) as out:
        for i, block in enumerate(blocks):
            samples, sr = sf.read(block["audio"], dtype="int16")
            if sr != 24000 or len(samples) == 0:
                raise ValueError("Invalid normalized narration")
            block["offset"] = clock / 24000
            block["duration"] = len(samples) / 24000
            out.write(samples)
            clock += len(samples)
            if i < len(blocks) - 1:
                out.write(np.zeros(pause, dtype=np.int16))
                clock += pause
    source = cfg["build"] / "narration_source.wav"
    temporary.replace(source)
    speed = cfg.get("playback_speed", 1.0)
    if speed == 1:
        shutil.copy2(source, master)
        output_duration = clock / 24000
    else:
        from .retime import retime_audio

        output_duration = retime_audio(source, master, speed)
    manifest = {
        "schema": 1,
        "voice_identity": identity,
        "blocks": blocks,
        "duration": output_duration,
        "source_duration": clock / 24000,
        "source_audio_sha256": file_hash(source),
        "playback_speed": speed,
        "sample_rate": 24000,
        "audio_sha256": file_hash(master),
        "script_sha256": file_hash(cfg["script_path"]),
        "voice_config_hash": digest(cfg["voice"]),
        "pause_between_blocks": cfg.get("pause_between_blocks", 0.35),
    }
    write_json(cfg["build"] / "narration_manifest.json", manifest)
    return manifest


def execute(cfg, stage):
    cfg["build"].mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    status = cfg["build"] / "status.json"
    write_json(status, {"stage": stage, "status": "running"})
    try:
        if stage in ("build", "synthesize"):
            manifest = synthesize(cfg)
            if stage == "synthesize":
                write_json(
                    status,
                    {
                        "stage": stage,
                        "status": "complete",
                        "duration": manifest["duration"],
                    },
                )
                return
        else:
            manifest = read_json(cfg["build"] / "narration_manifest.json")
            if manifest["script_sha256"] != file_hash(cfg["script_path"]):
                raise ValueError(
                    "Script changed; run build/synthesize before alignment or export"
                )
            if manifest["audio_sha256"] != file_hash(cfg["build"] / "narration.wav"):
                raise ValueError(
                    "Narration changed; regenerate its manifest and alignment"
                )
            if manifest.get("voice_config_hash") != digest(
                cfg["voice"]
            ) or manifest.get("pause_between_blocks") != cfg.get(
                "pause_between_blocks", 0.35
            ):
                raise ValueError(
                    "Voice settings or pauses changed; run build/synthesize first"
                )
            if manifest.get("playback_speed", 1.0) != cfg.get("playback_speed", 1.0):
                raise ValueError("Playback speed changed; run build/synthesize first")
        cfg["duration"] = manifest["duration"]
        if stage in ("build", "align"):
            from .alignment import align_blocks
            from .timeline import compile_timeline, to_srt

            blocks = align_blocks(manifest["blocks"], cfg)
            source_cfg = {
                **cfg,
                "duration": manifest.get("source_duration", manifest["duration"]),
            }
            timeline = compile_timeline(blocks, cfg["cues"], source_cfg)
            if cfg.get("playback_speed", 1.0) != 1:
                from .retime import retime_timeline

                timeline = retime_timeline(
                    timeline, cfg["playback_speed"], manifest["duration"]
                )
            timeline["audio_sha256"] = manifest["audio_sha256"]
            timeline["timing_spec_hash"] = timing_spec(cfg)
            write_json(cfg["build"] / "timeline.json", timeline)
            (cfg["build"] / "subtitles.srt").write_text(
                to_srt(timeline), encoding="utf-8"
            )
        else:
            timeline = read_json(cfg["build"] / "timeline.json")
            if timeline["audio_sha256"] != manifest["audio_sha256"]:
                raise ValueError("Timeline refers to different audio; run align first")
            if timeline.get("timing_spec_hash") != timing_spec(cfg):
                raise ValueError(
                    "Cue/alignment/subtitle settings changed; run align first"
                )
        from .render import write_review

        write_review(cfg, timeline)
        if stage in ("build", "render"):
            from .render import export_video, render_deck

            slides = render_deck(cfg, timeline)
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] EXPORT rendering video to narration clock",
                flush=True,
            )
            output = export_video(cfg, timeline, slides)
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] VIDEO {output}",
                flush=True,
            )
        write_json(
            status,
            {
                "stage": stage,
                "status": "complete",
                "elapsed_seconds": time.monotonic() - started,
            },
        )
    except Exception as e:
        write_json(
            status,
            {
                "stage": stage,
                "status": "failed",
                "error": str(e),
                "elapsed_seconds": time.monotonic() - started,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Cloned narration → forced alignment → semantic PPT timing → video"
    )
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ["check", "build", "synthesize", "align", "render"]:
        p = subs.add_parser(name)
        p.add_argument("project", type=Path)
    preview = subs.add_parser("serve")
    preview.add_argument("project", type=Path)
    preview.add_argument("--port", type=int, default=8766)
    voice = subs.add_parser("voice-import")
    voice.add_argument("audio", type=Path)
    voice.add_argument("--transcript", type=Path, required=True)
    voice.add_argument("--name", required=True)
    voice.add_argument("--url", default="http://127.0.0.1:3900")
    args = parser.parse_args()
    if args.command == "voice-import":
        print(
            json.dumps(
                OmniVoice({"base_url": args.url}).import_voice(
                    args.audio, args.transcript.read_text(), args.name
                ),
                ensure_ascii=False,
            )
        )
        return
    cfg = load_project(args.project)
    if args.command == "serve":
        from .server import serve

        serve(cfg["root"], args.port)
        return
    if args.command == "check":
        service = OmniVoice(cfg["voice"])
        info = service.json("/system/info")
        print(
            json.dumps(
                {
                    "device": info.get("device"),
                    "identity": service.identity(),
                    "model": service.json("/model/status"),
                    "blocks": len(cfg["blocks"]),
                    "cues": len(cfg["cues"]),
                    "tools": {
                        t: shutil.which(t) for t in ["ffmpeg", "ffprobe", "node"]
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    # An OS advisory lock releases automatically on crashes; concurrent builds must not mix artifacts.
    import fcntl

    cfg["build"].mkdir(parents=True, exist_ok=True)
    with (cfg["build"] / ".build.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error(
                "Another build is already using this project's output directory"
            )
        execute(cfg, args.command)


if __name__ == "__main__":
    main()
