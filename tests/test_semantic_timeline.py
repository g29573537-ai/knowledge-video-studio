from narration_video.core import parse_script

from knowledge_video.semantic_timeline import (
    build_semantic_timeline,
    resolve_anchor,
    validate_semantic_timeline,
)


def aligned_block():
    b = parse_script("## intro\n[[first]]声音先行，[[second]]画面跟随。")[0]
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
    b["slide_id"] = "slide-1"
    b["headline"] = "声音与画面"
    b["source_ids"] = ["S1"]
    return b


def test_resolve_anchor_maps_phrase_to_chars_and_time():
    b = aligned_block()
    anchor = resolve_anchor("画面跟随", b["text"], b["chars"], b["offset"])
    assert anchor["char_start"] == 4
    assert anchor["char_end"] == 7
    assert anchor["time_start"] == 5.6


def test_unresolved_anchor_blocks_export():
    b = aligned_block()
    try:
        resolve_anchor("不存在的短语", b["text"], b["chars"], b["offset"])
    except ValueError as exc:
        assert "Unresolved" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_semantic_timeline_separates_media_source_and_camera_view():
    b = aligned_block()
    timeline = build_semantic_timeline([b], aligned_blocks=[b])
    assert timeline["semantic_version"] == 1
    beat = timeline["scenes"][0]["beats"][0]
    assert beat["media_source"]["type"] != beat["camera_plan"][0]["view"]
    assert beat["camera_plan"][0]["view"] == "overview"
    assert beat["word_start"] == 0
    validate_semantic_timeline(timeline)


def test_missing_acoustic_anchor_is_rejected():
    b = aligned_block()
    b["chars"][0]["valid"] = False
    try:
        build_semantic_timeline([b], aligned_blocks=[b])
    except ValueError as exc:
        assert "acoustic" in str(exc) or "anchor" in str(exc).lower()
    else:
        raise AssertionError("invalid acoustic anchor must block semantic timeline")
