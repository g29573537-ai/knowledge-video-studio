import io
import wave

import pytest

from narration_video.voice import OmniVoice


def wav():
    b = io.BytesIO()
    with wave.open(b, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b"\x00\x00" * 2400)
    return b.getvalue()


def test_cache_tracks_text_speed_reference_and_partial_download(tmp_path, monkeypatch):
    client = OmniVoice({"mode": "design"})
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return wav()

    monkeypatch.setattr(client, "request", request)
    identity = {"ref": "version1"}
    a, hit = client.synthesize("一句话", tmp_path, identity)
    assert not hit
    assert client.synthesize("一句话", tmp_path, identity)[1]
    assert len(calls) == 1
    client.synthesize("另一句话", tmp_path, identity)
    client.config["speed"] = 1.2
    client.synthesize("一句话", tmp_path, identity)
    client.synthesize("一句话", tmp_path, {"ref": "version2"})
    assert len(calls) == 4
    client.config["speed"] = 1.0
    a.write_bytes(b"interrupted download")
    assert not client.synthesize("一句话", tmp_path, identity)[1]
    assert len(calls) == 5


def test_invalid_audio_never_enters_cache(tmp_path, monkeypatch):
    client = OmniVoice({"mode": "design"})
    monkeypatch.setattr(client, "request", lambda *a, **kw: b'{"error":"not audio"}')
    with pytest.raises(Exception):
        client.synthesize("测试", tmp_path, {})
    assert not list(tmp_path.glob("*.wav"))
    assert not list(tmp_path.glob("*.json"))


def test_clone_does_not_fall_back_to_default(monkeypatch):
    with pytest.raises(ValueError, match="explicit"):
        OmniVoice({"mode": "clone"}).identity()
    c = OmniVoice({"mode": "clone", "profile_id": "missing"})
    monkeypatch.setattr(c, "json", lambda route: {"id": "missing"})
    with pytest.raises(ValueError, match="reference audio"):
        c.identity()


def test_unloaded_backend_fails_before_cold_inference(monkeypatch):
    c = OmniVoice({"mode": "design"})
    monkeypatch.setattr(
        c,
        "json",
        lambda route: {"loaded": False, "loading": False, "detail": "Model ready"},
    )
    with pytest.raises(RuntimeError, match="not warmed up"):
        c.wait_ready()


def test_backend_loading_waits_for_actual_loaded_flag(monkeypatch):
    c = OmniVoice({"mode": "design"})
    statuses = iter(
        [
            {"loaded": False, "loading": True, "detail": "Loading weights"},
            {"loaded": True},
        ]
    )
    monkeypatch.setattr(c, "json", lambda route: next(statuses))
    monkeypatch.setattr("narration_video.voice.time.sleep", lambda seconds: None)
    c.wait_ready()
