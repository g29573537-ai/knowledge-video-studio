import threading

import pytest
from pydantic import BaseModel

from knowledge_video.models import JobRequest, ProviderConfig
from knowledge_video.run_state import RunStore, fingerprint_inputs
from knowledge_video.workflow import Workflow


class M(BaseModel):
    value: int = 0


def test_fingerprint_inputs_canonicalizes_order():
    a = fingerprint_inputs({"b": 2, "a": 1})
    b = fingerprint_inputs({"a": 1, "b": 2})
    assert a == b
    assert len(a) == 64


def test_run_store_resume_marks_stale_run_interrupted(tmp_path):
    store = RunStore(tmp_path, ttl_seconds=0)
    store.start({"x": 1})
    # Force stale heartbeat.
    import json
    import time

    data = json.loads((tmp_path / "run_state.json").read_text())
    data["heartbeat_at"] = time.time() - 10
    (tmp_path / "run_state.json").write_text(json.dumps(data))
    resumed = store.resume()
    assert resumed["status"] == "interrupted"


def test_run_store_artifact_integrity_detects_tampering(tmp_path):
    p = tmp_path / "artifact.txt"
    p.write_text("hello")
    store = RunStore(tmp_path)
    info = store.record_artifact("a", p)
    assert info
    assert store.stage_completed("missing") is False
    store.record_stage("stage1", artifacts={"a": p})
    assert store.stage_completed("stage1") is True
    p.write_text("tampered")
    assert store.stage_completed("stage1") is False


def test_workflow_llm_reuses_only_matching_fingerprint(tmp_path, monkeypatch):
    request = JobRequest(topic="test topic", provider=ProviderConfig(kind="codex"))
    cancel = threading.Event()
    wf = Workflow(tmp_path, request, lambda *a, **k: None, cancel)
    wf.provider.generate = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("should not run")
    )

    target = tmp_path / "cached.json"
    target.write_text('{"value": 5}')
    fp = fingerprint_inputs(
        {
            "instruction": "inst",
            "payload": {"x": 1},
            "schema": M.model_json_schema(),
            "model": "",
            "provider_kind": "codex",
            "temperature": None,
            "images": None,
        }
    )
    (tmp_path / "cached.fingerprint.json").write_text('{"fingerprint": "%s"}' % fp)  # noqa: UP031

    result = wf.llm("cached", "inst", {"x": 1}, M)
    assert result.value == 5

    with pytest.raises(RuntimeError, match="should not run"):
        wf.llm("cached", "inst", {"x": 2}, M)
