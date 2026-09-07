import importlib.util
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from knowledge_video.models import JobRequest, ResearchPlan
from knowledge_video.workflow import Workflow
from knowledge_video.server import create_app
from knowledge_video.model_manager import ModelManager
from narration_video.voice import OmniVoice
from narration_video.timeline import subtitle_spans
from narration_video.core import normalized


def test_language_is_validated_and_reaches_provider(tmp_path, monkeypatch):
    request = JobRequest(
        topic="A simple lesson",
        language="en",
        reference_language="zh",
        asr_model="medium",
    )
    workflow = Workflow(tmp_path, request, lambda *a, **kw: None, threading.Event())
    captured = []

    def generate(instruction, payload, model, images):
        captured.append(instruction)
        return ResearchPlan(
            title="Example", learning_goal="Learn", outline=[], candidate_urls=[]
        )

    monkeypatch.setattr(workflow.provider, "generate", generate)
    workflow.llm("plan", "Instruction", {}, ResearchPlan)
    assert "English（en）" in captured[0]
    with pytest.raises(ValidationError):
        JobRequest(topic="Unsupported", language="unknown")


def test_reference_language_does_not_replace_target_language(tmp_path, monkeypatch):
    client = OmniVoice({"language": "en", "reference_language": "zh"})
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")
    requests = []

    def capture(route, data=None, *args, **kwargs):
        requests.append(data)
        return b'{"id":"profile"}'

    monkeypatch.setattr(client, "request", capture)
    client.import_voice(audio, "录音实际内容", "My voice")
    assert b'name="language"\r\n\r\nzh\r\n' in requests[0]
    assert client.config["language"] == "en"


def test_english_subtitles_keep_spaces_and_words():
    text = "This simple example explains how costs can change a trading result."
    chars = [
        {
            "char": c,
            "valid": True,
            "start": i * 0.05,
            "end": i * 0.05 + 0.04,
            "score": 0.9,
        }
        for i, c in enumerate(normalized(text))
    ]
    spans = subtitle_spans(text, 30, chars)
    assert normalized("".join(s[0] for s in spans)) == normalized(text)
    words = text.split()
    assert [w for s in spans for w in s[0].split()] == words


def test_model_preparation_rejects_arbitrary_models_and_stale_receipts(tmp_path):
    manager = ModelManager(tmp_path)
    with pytest.raises(ValueError):
        manager.start("bogus", "small", "download", "http://localhost:3900")
    (manager.root / "en-small.json").write_text(
        json.dumps(
            {
                "language": "en",
                "asr_model": "small",
                "files": [{"path": str(tmp_path / "missing"), "size": 1}],
            }
        )
    )
    assert manager.catalog()["prepared"] == []


def test_model_endpoint_blocks_while_video_job_active(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    monkeypatch.setattr(app.state.jobs, "list", lambda: [{"status": "running"}])
    with TestClient(app) as client:
        assert "en" in client.get("/api/voice/models").json()["languages"]
        r = client.post(
            "/api/voice/models/prepare",
            headers={"X-Studio-Client": "1"},
            json={"language": "en", "action": "load"},
        )
        assert r.status_code == 409


def test_installer_plan_pins_omni_and_uses_private_environment(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/install.py"
    spec = importlib.util.spec_from_file_location("studio_installer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module.commands(tmp_path)
    assert plan[2][0][-1] == module.OMNI_REV
    assert "--frozen" in plan[4][0]
    assert str(tmp_path / ".runtime/omnivoice/.venv/bin/python") in plan[-1][0]
    assert not (tmp_path / ".runtime").exists()
