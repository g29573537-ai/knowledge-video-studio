import copy

import pytest

from narration_video.alignment import extract_chars
from narration_video.core import parse_script
from narration_video.timeline import compile_timeline, subtitle_spans, to_srt
from narration_video.render import visual_intervals


def test_markers_never_split_natural_narration():
    b = parse_script("# title\n## intro\n[[a]]先听声音，[[b]]再看画面。")
    assert len(b) == 1
    assert b[0]["text"] == "先听声音，再看画面。"
    assert b[0]["cues"] == [{"id": "a", "char_index": 0}, {"id": "b", "char_index": 4}]


@pytest.mark.parametrize(
    "text",
    [
        "## x\n[[a]]一[[a]]二",
        "## x\n一[[end]]",
        "## x\n[[broken cue]]一",
        "## x\n一\n## x\n二",
    ],
)
def test_invalid_anchors_fail_before_tts(text):
    with pytest.raises(ValueError):
        parse_script(text)


def aligned_block():
    b = parse_script("## intro\n[[first]]声音先行，[[second]]画面跟随。")[0]
    # Real acoustic timings are non-uniform and include a long rhetorical pause.
    starts = [0.4, 0.6, 0.9, 1.1, 3.6, 3.8, 4.2, 4.4]
    b.update(
        offset=2.0,
        duration=5.0,
        coverage=1.0,
        chars=[
            {"char": c, "start": t, "end": t + 0.15, "score": 0.9, "valid": True}
            for c, t in zip("声音先行画面跟随", starts)
        ],
    )
    return b


def test_audio_timing_drives_cues_and_subtitles_not_equal_duration():
    b = aligned_block()
    t = compile_timeline(
        [b], {"first": {"slide": "a"}, "second": {"slide": "b"}}, {"duration": 7}
    )
    assert [e["time"] for e in t["events"]] == [2.4, 5.6]
    assert t["subtitles"][1]["start"] == 5.6
    assert "00:00:05,600" in to_srt(t)
    intervals = visual_intervals(t)
    assert sum(i["end"] - i["start"] for i in intervals) == pytest.approx(7)
    assert any(i["text"] == "" and i["end"] - i["start"] > 2 for i in intervals)


def test_speech_rate_change_retimes_all_semantic_cues():
    b = aligned_block()
    for c in b["chars"]:
        c["start"] /= 2
        c["end"] /= 2
    b["duration"] /= 2
    t = compile_timeline([b], {"first": {}, "second": {}}, {"duration": 4.5})
    assert [e["time"] for e in t["events"]] == [2.2, 3.8]


def test_low_confidence_cue_blocks_export():
    b = aligned_block()
    b["chars"][4]["score"] = 0.01
    with pytest.raises(ValueError, match="reliable acoustic"):
        compile_timeline([b], {"first": {}, "second": {}}, {"duration": 7})


def test_missing_word_is_not_silently_interpolated():
    raw = {
        "segments": [
            {"chars": [{"char": "声", "start": 0.2, "end": 0.4, "score": 0.9}]}
        ]
    }
    with pytest.raises(ValueError, match="exact spoken script"):
        extract_chars(raw, "声音", 1)


def test_unscored_acoustic_output_fails_coverage():
    raw = {"segments": [{"chars": [{"char": "声"}, {"char": "音"}]}]}
    with pytest.raises(ValueError, match="coverage"):
        extract_chars(raw, "声音", 1)


def test_cue_lead_cannot_reverse_order():
    b = aligned_block()
    b["chars"][4]["start"] = 0.5
    with pytest.raises(ValueError, match="collide"):
        compile_timeline(
            [b], {"first": {}, "second": {"lead_seconds": 0.8}}, {"duration": 7}
        )


def test_zero_subtitle_width_fails_instead_of_looping():
    with pytest.raises(ValueError, match="positive integer"):
        subtitle_spans("这是一句话。", 0)


def test_caption_merges_weak_onset_without_inventing_time_or_dropping_text():
    text = "先扣费用，还剩九元。"
    chars = [{"valid": True} for _ in "先扣费用还剩九元"]
    chars[4]["valid"] = False
    spans = subtitle_spans(text, 25, chars)
    assert "".join(s[0] for s in spans) == text
    assert spans == [(text, 0, 7)]
    assert all(
        chars[first]["valid"] and chars[last]["valid"] for _, first, last in spans
    )


def test_caption_cannot_hide_unreliable_block_start():
    with pytest.raises(ValueError, match="reliable subtitle boundaries"):
        subtitle_spans(
            "大家好。", 25, [{"valid": False}, {"valid": True}, {"valid": True}]
        )


def test_acoustic_captions_respect_width_and_preserve_punctuation():
    text = "买入以后，报价可能已经改变。我们需要检查实际成交。"
    chars = [{"valid": True} for c in text if c.isalnum()]
    spans = subtitle_spans(text, 12, chars)
    assert "".join(s[0] for s in spans) == text
    assert all(len(s[0]) <= 12 for s in spans)
