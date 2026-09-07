import json
import threading

import pytest

from knowledge_video.models import Block, JobRequest, Lesson, ResearchPlan, Review
from knowledge_video.workflow import Workflow


@pytest.mark.parametrize(
    "source_case", ["no_candidates", "failed_fetch", "cached_empty"]
)
def test_without_sources_reaches_reviewed_lesson(tmp_path, monkeypatch, source_case):
    import knowledge_video.workflow as w

    browser = tmp_path / "chrome"
    browser.touch()
    monkeypatch.setattr(w.shutil, "which", lambda tool: str(browser))
    monkeypatch.setattr(w.OmniVoice, "wait_ready", lambda self: None)
    calls = []

    def fetch(url):
        calls.append(url)
        raise ValueError("unavailable")

    monkeypatch.setattr(w, "fetch_source", fetch)
    if source_case == "cached_empty":
        (tmp_path / "sources.json").write_text("[]")
    plan = ResearchPlan(
        title="基础算例",
        learning_goal="学会计算",
        outline=["概念", "算例"],
        candidate_urls=[]
        if source_case == "no_candidates"
        else ["https://example.org/source"],
    )
    lesson = Lesson(
        title="基础算例",
        description="用假设数据说明计算。",
        uncertainties=[],
        blocks=[
            Block(
                id=f"b{i}",
                slide_id=f"s{i}",
                narration="这里使用明确标注的假设数据，逐步计算并说明每一步的含义。",
                headline="计算",
                points=["假设数据"],
                source_ids=[],
            )
            for i in (1, 2)
        ],
    )
    workflow = Workflow(
        tmp_path,
        JobRequest(topic="基础知识", chrome=str(browser)),
        lambda *a, **kw: None,
        threading.Event(),
    )

    def llm(name, instruction, payload, model, images=None):
        if name == "research_plan":
            return plan
        assert payload["sources"] == []
        assert payload["knowledge_basis"] == "general_knowledge"
        if name == "lesson_draft":
            return lesson
        assert name == "editor_review"
        return Review(approved=True, issues=[], lesson=lesson)

    class ReachedSlides(Exception):
        pass

    def step(name, message):
        if name == "slides":
            raise ReachedSlides()

    monkeypatch.setattr(workflow, "llm", llm)
    monkeypatch.setattr(workflow, "step", step)
    with pytest.raises(ReachedSlides):
        workflow.run()
    assert json.loads((tmp_path / "sources.json").read_text()) == []
    assert (
        json.loads((tmp_path / "research_basis.json").read_text())["mode"]
        == "general_knowledge"
    )
    saved = json.loads((tmp_path / "lesson.json").read_text())
    assert any("未使用外部核验资料" in note for note in saved["uncertainties"])
    assert all(b["source_ids"] == [] for b in saved["blocks"])
    assert len(calls) == (1 if source_case == "failed_fetch" else 0)
