import wave
from pathlib import Path

from PIL import Image

from narration_video.core import probe
from narration_video.render import export_video
from narration_video.qc import run_qc


def make_export(tmp_path, duration=2.37):
    with wave.open(str(tmp_path / "narration.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(b"\x00\x00" * round(duration * 24000))
    slides = []
    for i, color in enumerate(["#202020", "#304050", "#506070"]):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (640, 360), color).save(p)
        slides.append(p)
    t = {
        "duration": duration,
        "events": [{"time": 0.13}, {"time": 1.47}],
        "subtitles": [
            {"start": 0.13, "end": 0.9, "text": "真实时间"},
            {"start": 1.61, "end": 2.22, "text": "保留停顿"},
        ],
    }
    cfg = {
        "build": tmp_path,
        "width": 640,
        "height": 360,
        "fps": 30,
        "subtitle": {"font_size": 20},
    }
    out = export_video(cfg, t, slides)
    return cfg, t, out


def test_valid_mini_mp4_passes(tmp_path):
    cfg, t, out = make_export(tmp_path)
    report = run_qc(cfg, t, out)
    assert report["passed"] is True
    assert (tmp_path / "qc_report.json").exists()


def test_corrupted_mp4_fails(tmp_path):
    cfg, t, out = make_export(tmp_path)
    data = out.read_bytes()
    out.write_bytes(data[:-1000])
    try:
        run_qc(cfg, t, out)
    except ValueError:
        pass
    else:
        raise AssertionError("corrupted mp4 should fail")


def test_wrong_fps_or_frame_count_fails(tmp_path):
    cfg, t, out = make_export(tmp_path)
    cfg2 = dict(cfg)
    cfg2["fps"] = 60
    try:
        run_qc(cfg2, t, out)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong fps should fail")


def test_audio_duration_mismatch_fails(tmp_path):
    cfg, t, out = make_export(tmp_path)
    t2 = dict(t)
    t2["duration"] = t["duration"] + 1.0
    try:
        run_qc(cfg, t2, out)
    except ValueError:
        pass
    else:
        raise AssertionError("audio duration mismatch should fail")


def test_missing_source_asset_fails(tmp_path):
    cfg, t, out = make_export(tmp_path)
    cfg["source_assets"] = [{"path": str(tmp_path / "missing.png"), "sha256": "abc"}]
    try:
        run_qc(cfg, t, out)
    except ValueError:
        pass
    else:
        raise AssertionError("missing source asset should fail")
