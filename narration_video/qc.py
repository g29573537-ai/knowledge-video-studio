"""Final technical QC for rendered knowledge videos."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from .render import visual_intervals


def _probe(path: Path) -> dict:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def _full_decode(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _extract_frame(path: Path, output: Path, timestamp: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _source_assets(cfg: dict, source_assets=None) -> list[dict]:
    items = source_assets
    if items is None:
        items = cfg.get("source_assets", [])
    result = []
    for item in items or []:
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append({"path": str(item)})
    return result


def run_qc(
    cfg: dict,
    timeline: dict,
    video_path: str | Path,
    slides=None,
    source_assets=None,
    report_path=None,
) -> dict:
    video_path = Path(video_path)
    build = Path(cfg.get("build", video_path.parent))
    build.mkdir(parents=True, exist_ok=True)
    report_file = Path(report_path) if report_path else build / "qc_report.json"
    failures: list[str] = []
    info = None
    video = None
    audio = None
    try:
        info = _probe(video_path)
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if video is None:
            failures.append("missing video stream")
        if audio is None:
            failures.append("missing audio stream")

        width = int(cfg.get("width", 1920))
        height = int(cfg.get("height", 1080))
        fps = int(cfg.get("fps", 30))
        duration = float(timeline.get("duration", 0.0))

        if video is not None:
            if (
                int(video.get("width", 0)) != width
                or int(video.get("height", 0)) != height
            ):
                failures.append("video dimensions mismatch")
            try:
                actual_fps = float(Fraction(video.get("r_frame_rate", "0/1")))
            except (ValueError, ZeroDivisionError):
                actual_fps = 0.0
            if abs(actual_fps - fps) > 0.01:
                failures.append("video FPS mismatch")
            nb_frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
            expected_frames = round(duration * fps)
            if abs(nb_frames - expected_frames) > 1:
                failures.append(
                    f"frame count mismatch: {nb_frames} != {expected_frames}"
                )
        if info is not None:
            try:
                format_duration = float(info.get("format", {}).get("duration", 0.0))
            except (TypeError, ValueError):
                format_duration = 0.0
            if abs(format_duration - duration) > 2 / fps + 0.03:
                failures.append("container duration mismatch")
        if audio is not None:
            try:
                audio_duration = float(audio.get("duration", 0.0))
            except (TypeError, ValueError):
                audio_duration = 0.0
            if abs(audio_duration - duration) > 0.1:
                failures.append("audio duration mismatch")
            if int(audio.get("sample_rate", 0) or 0) < 8000:
                failures.append("audio sample rate invalid")

        # Full decode must succeed.
        try:
            _full_decode(video_path)
        except subprocess.CalledProcessError as exc:
            failures.append(
                "full decode failed: "
                + (
                    exc.stderr.decode(errors="replace")[-500:]
                    if exc.stderr
                    else str(exc)
                )
            )

        # Source integrity.
        for item in _source_assets(cfg, source_assets):
            path = Path(item.get("path", ""))
            if not path or not path.exists():
                failures.append(f"missing source asset: {path}")
                continue
            expected_sha = item.get("sha256")
            if expected_sha:
                from narration_video.core import file_hash

                if file_hash(path) != expected_sha:
                    failures.append(f"source hash mismatch: {path}")

        # Visual interval continuity.
        try:
            intervals = visual_intervals(timeline)
            cursor = 0.0
            for interval in intervals:
                if interval["start"] - cursor > 0.05:
                    failures.append("gap in visual intervals")
                    break
                cursor = interval["end"]
            if intervals and abs(cursor - duration) > 0.05:
                failures.append("visual intervals do not reach narration end")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"visual interval check failed: {exc}")

        # Extract sample and caption frames.
        sample_frames = []
        frame_dir = build / "qc_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        try:
            times = [0.0, duration / 2, max(0.0, duration - 0.1)]
            subtitles = timeline.get("subtitles", []) or []
            if subtitles:
                times.append(float(subtitles[len(subtitles) // 2].get("start", 0.0)))
            for i, t in enumerate(times):
                out = frame_dir / f"sample_{i}.png"
                _extract_frame(video_path, out, t)
                sample_frames.append(str(out))
        except subprocess.CalledProcessError as exc:
            failures.append(
                "frame extraction failed: "
                + (
                    exc.stderr.decode(errors="replace")[-300:]
                    if exc.stderr
                    else str(exc)
                )
            )

        passed = not failures
        report = {
            "passed": passed,
            "technical_passed": passed,
            "failures": failures,
            "video": str(video_path),
            "duration": duration,
            "container_duration": float(info.get("format", {}).get("duration", 0.0))
            if info
            else None,
            "video_width": video.get("width") if video else None,
            "video_height": video.get("height") if video else None,
            "fps": video.get("r_frame_rate") if video else None,
            "frame_count": int(
                video.get("nb_read_frames") or video.get("nb_frames") or 0
            )
            if video
            else None,
            "sample_frames": sample_frames,
        }
        from .core import write_json

        write_json(report_file, report)
        if not passed:
            raise ValueError("Final QC failed: " + "; ".join(failures))
        return report
    except ValueError:
        raise
    except Exception as exc:
        report = {
            "passed": False,
            "technical_passed": False,
            "failures": [str(exc)],
            "video": str(video_path),
        }
        from .core import write_json

        write_json(report_file, report)
        raise ValueError(f"Final QC failed: {exc}") from exc


# Compatibility aliases.
validate_export = run_qc
qc_video = run_qc
verify_export = run_qc
