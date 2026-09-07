import pytest

from narration_video.alignment import extract_chars


def test_high_overall_coverage_cannot_hide_an_omitted_phrase():
    text = "这是完整的口播内容" * 10
    chars = [
        {
            "char": c,
            "start": i * 0.1,
            "end": (i + 1) * 0.1,
            "score": 0 if 20 <= i < 25 else 0.99,
        }
        for i, c in enumerate(text)
    ]
    raw = {"segments": [{"chars": chars}]}
    with pytest.raises(ValueError, match="omitted phrase"):
        extract_chars(raw, text, len(text) * 0.1)


def test_isolated_weak_syllables_remain_usable():
    text = "这是完整的口播内容" * 10
    chars = [
        {
            "char": c,
            "start": i * 0.1,
            "end": (i + 1) * 0.1,
            "score": 0 if i in (20, 21) else 0.99,
        }
        for i, c in enumerate(text)
    ]
    result = extract_chars({"segments": [{"chars": chars}]}, text, len(text) * 0.1)
    assert result["coverage"] > 0.9
