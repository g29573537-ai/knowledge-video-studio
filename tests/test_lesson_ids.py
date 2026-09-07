import pytest

from knowledge_video.decks import normalize_lesson_ids, validate_lesson
from knowledge_video.models import Block, Lesson
from narration_video.core import parse_script


def make_lesson(ids):
    return Lesson(
        title="讲稿编号",
        description="验证编号兼容性。",
        uncertainties=[],
        blocks=[
            Block(id=value, slide_id=f"slide-{i}", headline="讲解",
                  narration="这里是一段完整的教学口播，用于验证页面与声音的对应关系。",
                  points=["保留内容"], source_ids=["U1"])
            for i, value in enumerate(ids, 1)
        ],
    )


def test_normalization_reserves_valid_ids_and_preserves_content():
    lesson = make_lesson(["block-1", "block_1", "block_1", "BLOCK 1", "", "中文", "9", "a" * 80])
    raw = lesson.model_dump()
    fixed, changes = normalize_lesson_ids(lesson)
    validate_lesson(fixed)
    assert fixed.blocks[1].id == "block_1"
    assert fixed.blocks[0].id == "block_1_2"
    assert len(changes) == 7
    assert lesson.model_dump() == raw
    for before, after in zip(lesson.blocks, fixed.blocks):
        assert before.model_dump(exclude={"id"}) == after.model_dump(exclude={"id"})
    again, _ = normalize_lesson_ids(lesson)
    assert again == fixed
    assert normalize_lesson_ids(fixed) == (fixed, [])
    script = "\n\n".join(f"## {b.id}\n[[{b.id}]]{b.narration}" for b in fixed.blocks)
    parsed = parse_script(script)
    assert [b["id"] for b in parsed] == [b.id for b in fixed.blocks]
    assert [b["cues"][0]["id"] for b in parsed] == [b.id for b in fixed.blocks]


def test_valid_ids_and_existing_html_mapping_are_preserved():
    lesson = make_lesson(["intro", "block_2"])
    fixed, changes = normalize_lesson_ids(lesson)
    assert fixed == lesson
    assert changes == []
    existing = {"slides": [{"id": b.slide_id} for b in lesson.blocks]}
    validate_lesson(fixed, existing)
    lesson.blocks[0].id = "block-1"
    fixed, changes = normalize_lesson_ids(lesson)
    validate_lesson(fixed, existing)
    assert changes[0]["slide_id"] == "slide-1"
    existing["slides"].reverse()
    with pytest.raises(ValueError, match="页序"):
        validate_lesson(fixed, existing)


def test_duplicate_pages_still_require_a_content_fix():
    lesson = make_lesson(["block-1", "block-1"])
    lesson.blocks[1].slide_id = lesson.blocks[0].slide_id
    fixed, _ = normalize_lesson_ids(lesson)
    with pytest.raises(ValueError, match="页面 id"):
        validate_lesson(fixed)
