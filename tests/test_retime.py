import json

import numpy as np
import pytest
import soundfile as sf

from narration_video.retime import retime_audio, retime_timeline


def test_real_tempo_change_preserves_pitch_and_moves_speech_onsets(tmp_path):
    sr = 24000
    signal = np.zeros(3 * sr)
    t = np.arange(sr) / sr
    signal[sr : 2 * sr] = 0.3 * np.sin(2 * np.pi * 440 * t)
    source, output = tmp_path / "source.wav", tmp_path / "faster.wav"
    sf.write(source, signal, sr)
    duration = retime_audio(source, output, 1.5)
    faster, rate = sf.read(output)
    assert duration == 2 and len(faster) == 2 * sr and rate == sr
    # Both ends of the audible interval follow the same clock as slide/caption cues.
    active = np.where(np.abs(faster) > 0.1)[0] / sr
    assert abs(active[0] - 1 / 1.5) < 0.05
    assert abs(active[-1] - 2 / 1.5) < 0.05
    sample = faster[int(0.8 * sr) : int(1.2 * sr)]
    frequency = np.fft.rfftfreq(len(sample), 1 / sr)[
        np.argmax(np.abs(np.fft.rfft(sample)))
    ]
    assert abs(frequency - 440) < 4


def test_retime_keeps_captions_and_slide_cues_on_same_source_clock():
    original = {
        "duration": 9,
        "events": [{"time": 3, "spoken_time": 3.3, "score": 0.8}],
        "subtitles": [{"start": 3.3, "end": 6, "text": "费用合计六元"}],
        "blocks": [{"offset": 0, "duration": 9, "coverage": 0.98}],
    }
    frozen = json.dumps(original)
    result = retime_timeline(original, 1.5, 6)
    assert result["events"][0]["spoken_time"] == result["subtitles"][0]["start"]
    assert result["subtitles"][0]["end"] == 4
    assert result["blocks"][0]["duration"] == result["duration"] == 6
    assert result["events"][0]["score"] == 0.8
    assert json.dumps(original) == frozen


def test_changed_playback_speed_rejects_stale_audio(tmp_path):
    from narration_video.cli import execute
    from narration_video.core import digest, file_hash, write_json

    script = tmp_path / "script.md"
    script.write_text("## x\n[[a]]你好。")
    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"old-audio")
    cfg = {"build": tmp_path, "script_path": script, "voice": {}, "playback_speed": 1.5}
    write_json(
        tmp_path / "narration_manifest.json",
        {
            "script_sha256": file_hash(script),
            "audio_sha256": file_hash(audio),
            "voice_config_hash": digest({}),
            "pause_between_blocks": 0.35,
            "playback_speed": 1,
            "duration": 2,
        },
    )
    with pytest.raises(ValueError, match="Playback speed changed"):
        execute(cfg, "render")
