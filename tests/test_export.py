import wave

from PIL import Image

from narration_video.core import probe
from narration_video.render import export_video


def test_ffmpeg_export_preserves_whole_master_audio_and_clock(tmp_path):
    duration = 2.37
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
    info = probe(out)
    assert abs(float(info["format"]["duration"]) - duration) < 0.07
    assert {s["codec_type"] for s in info["streams"]} == {"audio", "video"}


def test_render_rejects_changed_cue_spec_before_overwriting(tmp_path):
    import pytest

    from narration_video.cli import execute
    from narration_video.core import digest, file_hash, write_json

    script = tmp_path / "script.md"
    script.write_text("## x\n[[a]]你好。")
    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"frozen-master")
    cfg = {
        "build": tmp_path,
        "script_path": script,
        "voice": {"profile_id": "test"},
        "cues": {"a": {"slide": "new"}},
    }
    write_json(
        tmp_path / "narration_manifest.json",
        {
            "script_sha256": file_hash(script),
            "audio_sha256": file_hash(audio),
            "voice_config_hash": digest(cfg["voice"]),
            "pause_between_blocks": 0.35,
            "duration": 2,
        },
    )
    write_json(
        tmp_path / "timeline.json",
        {"audio_sha256": file_hash(audio), "timing_spec_hash": "old"},
    )
    with pytest.raises(ValueError, match="settings changed"):
        execute(cfg, "render")
    assert not (tmp_path / "video.mp4").exists()
