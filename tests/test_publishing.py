import json
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from knowledge_video.models import JobRequest
from knowledge_video.publishing import (
    PublishingCopy,
    cover_html,
    description_text,
    generate,
)
from knowledge_video.server import create_app
from knowledge_video.workflow import chrome_path


def copy_fixture():
    return PublishingCopy(
        title="柠檬有什么特别",
        cover_title="柠檬的香气从哪来？",
        cover_subtitle="聊聊果皮、酸味和厨房里的小知识",
        introduction="这期介绍柠檬果皮的香气和果汁的酸味。结合厨房里的常见场景，说明这些特点可以怎样使用。",
        tags=["柠檬", "生活知识", "植物"],
    )


def test_description_keeps_real_timestamps_sources_and_limits():
    text = description_text(
        copy_fixture(),
        [{"time": 65.9, "title": "酸味"}],
        [{"title": "资料", "url": "https://example.org/lemon"}],
        ["未进行外部核验"],
    )
    assert "01:05 酸味" in text
    assert "https://example.org/lemon" in text
    assert "#柠檬" in text and "未进行外部核验" in text


@pytest.mark.parametrize("long_title", [False, True])
def test_real_cover_render_and_atomic_version(tmp_path, long_title):
    if not Path(chrome_path()).exists() or not shutil.which("node"):
        pytest.skip("Chrome and Node required")
    for name, data in {
        "lesson.json": {"title": "柠檬", "uncertainties": []},
        "chapters.json": [],
        "sources.json": [],
    }.items():
        (tmp_path / name).write_text(json.dumps(data))
    (tmp_path / "template.html").write_text(
        "<style>body{background:#191919}</style>Zero2Quant"
    )
    shots = tmp_path / "build/slides"
    shots.mkdir(parents=True)
    Image.new("RGB", (320, 180), "#191919").save(shots / "0000.png")
    copy = copy_fixture()
    if long_title:
        copy.cover_title = (
            "A practical introduction to lemons and their surprising uses"
        )
        copy.cover_subtitle = "Learn how citrus peel, juice and acidity work in everyday cooking, with examples you can follow at home."
    workflow = SimpleNamespace(
        root=tmp_path,
        request=JobRequest(topic="柠檬"),
        cancel=threading.Event(),
        llm=lambda *a, **kw: copy,
        notify=lambda *a, **kw: None,
    )
    result = generate(workflow)
    assert Image.open(tmp_path / result["cover_path"]).size == (1920, 1080)
    assert json.loads((tmp_path / "publishing.json").read_text()) == result
    assert (tmp_path / result["description_path"]).read_text() == result["description"]
    copy.cover_title = '<script>alert("x")</script>'
    assert "&lt;script&gt;" in cover_html(
        copy, shots / "0000.png", "background:#ffffff"
    )
    workflow.llm = lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("provider unavailable")
    )
    with pytest.raises(RuntimeError):
        generate(workflow)
    assert json.loads((tmp_path / "publishing.json").read_text()) == result


def test_completed_job_can_generate_without_touching_video_and_retry(
    tmp_path, monkeypatch
):
    from knowledge_video.workflow import Workflow

    id = "a" * 32
    root = tmp_path / "jobs" / id
    root.mkdir(parents=True)
    state = {
        "id": id,
        "status": "completed",
        "stage": "completed",
        "created": 0,
        "events": [],
        "result": {"title": "Original"},
    }
    (root / "status.json").write_text(json.dumps(state))
    (root / "request.json").write_text(JobRequest(topic="测试视频").model_dump_json())
    video = root / "build/video.mp4"
    video.parent.mkdir()
    video.write_bytes(b"unchanged video")
    monkeypatch.setattr(Workflow, "make_publication", lambda self: {"version": "v1"})
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.post(f"/api/jobs/{id}/publishing", json={}).status_code == 403
        assert (
            client.post(
                f"/api/jobs/{id}/publishing", headers={"X-Studio-Client": "1"}, json={}
            ).status_code
            == 200
        )

        def wait_done():
            for _ in range(100):
                if id not in app.state.jobs.running:
                    return app.state.jobs.get(id)
                time.sleep(0.01)
            pytest.fail("publishing worker did not finish")

        saved = wait_done()
        assert saved["publication"] == {"version": "v1"}
        assert saved["status"] == "completed" and saved["result"] == state["result"]
        monkeypatch.setattr(
            Workflow,
            "make_publication",
            lambda self: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        client.post(
            f"/api/jobs/{id}/publishing", headers={"X-Studio-Client": "1"}, json={}
        )
        saved = wait_done()
        assert saved["publishing"]["status"] == "failed"
        assert (
            saved["publication"] == {"version": "v1"}
            and video.read_bytes() == b"unchanged video"
        )
        folder = root / "publishing" / ("b" * 32)
        folder.mkdir(parents=True)
        (folder / "cover.png").write_bytes(b"png")
        (folder / "copy.json").write_text("private provider cache")
        base = f"/artifacts/{id}/publishing/" + "b" * 32
        assert client.get(base + "/cover.png").status_code == 200
        assert client.get(base + "/copy.json").status_code == 404
    app.state.jobs.pool.shutdown(wait=True)
