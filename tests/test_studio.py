import json, threading, time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from knowledge_video.server import create_app
from knowledge_video.models import JobRequest, ProviderConfig, ResearchPlan
from knowledge_video.providers import Provider
from knowledge_video.materials import bundle_html, inspect_slides

HEADERS = {"X-Studio-Client": "1"}


def test_existing_deck_import_copies_only_referenced_assets(tmp_path):
    root = tmp_path / "user"
    root.mkdir()
    (root / "site.css").write_text("body{background:url('bg.png')}")
    (root / "bg.png").write_bytes(b"image")
    (root / "private.env").write_text("secret")
    source = root / "slides.html"
    source.write_text(
        '<link href="site.css"><section id="one">第一页</section><section id="two">第二页</section>'
    )
    out = tmp_path / "copy" / "slides.html"
    out.parent.mkdir()
    bundle_html(source, out)
    assert len(inspect_slides(out)["slides"]) == 2
    assert len(list((out.parent / "assets").iterdir())) == 2
    assert not (out.parent / "private.env").exists()
    assert "private.env" not in out.read_text()


def test_existing_reveal_shows_all_fragment_groups_and_rejects_ambiguous_pages(
    tmp_path,
):
    from knowledge_video.decks import existing_deck

    source = tmp_path / "deck.html"
    source.write_text(
        '<section id="one"><p class="fragment" data-fragment-index="0">A</p><p class="fragment" data-fragment-index="0">B</p><p class="fragment">C</p></section><script>Reveal.initialize({})</script>'
    )
    info = inspect_slides(source)
    assert existing_deck(info, tmp_path / "copy.html")["one"]["f"] == 1
    source.write_text('<section id="same"></section><section id="same"></section>')
    with pytest.raises(ValueError, match="重复"):
        inspect_slides(source)
    source.write_text(
        "<section><section></section></section><script>Reveal.initialize({})</script>"
    )
    with pytest.raises(ValueError, match="嵌套"):
        inspect_slides(source)


def test_offline_font_keeps_available_woff_when_optional_ttf_is_missing(tmp_path):
    (tmp_path / "font.woff").write_bytes(b"font")
    (tmp_path / "style.css").write_text(
        '@font-face{font-family:test;src:url(font.eot);src:url(font.woff) format("woff"),url(font.ttf) format("truetype");font-weight:400}'
    )
    source = tmp_path / "deck.html"
    source.write_text('<link href="style.css"><section>test</section>')
    bundle_html(source, tmp_path / "copy/deck.html")
    css = next((tmp_path / "copy/assets").glob("*.css")).read_text()
    assert ".woff" in css and ".ttf" not in css and ".eot" not in css


def test_proxy_fake_dns_requires_public_resolution_and_still_rejects_private(
    tmp_path, monkeypatch
):
    import knowledge_video.materials as m

    monkeypatch.setattr(
        m.socket, "getaddrinfo", lambda *a: [(2, 1, 6, "", ("198.18.1.2", 443))]
    )

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Status": 0, "Answer": [{"type": 1, "data": "93.184.216.34"}]}

    monkeypatch.setattr(m.requests, "get", lambda *a, **kw: Response())
    assert m.public_url("https://example.com/page") == "https://example.com/page"
    with pytest.raises(ValueError, match="保留"):
        m.public_url("https://198.18.1.2")
    monkeypatch.setattr(
        Response,
        "json",
        lambda s: {"Status": 0, "Answer": [{"type": 1, "data": "127.0.0.1"}]},
    )
    with pytest.raises(ValueError, match="本地"):
        m.public_url("https://example.com")
    monkeypatch.setattr(
        m.socket, "getaddrinfo", lambda *a: [(2, 1, 6, "", ("192.168.1.2", 443))]
    )
    with pytest.raises(ValueError, match="本地"):
        m.public_url("https://example.com")


def test_api_rejects_cross_site_mutations_and_does_not_expose_job_secrets(
    tmp_path, monkeypatch
):
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post("/api/jobs", json={}).status_code == 403
    assert (
        client.post(
            "/api/jobs", headers={**HEADERS, "Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )
    monkeypatch.setattr(app.state.jobs, "start", lambda id: None)
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"placeholder")
    response = client.post(
        "/api/jobs",
        headers=HEADERS,
        json={
            "topic": "测试主题",
            "voice_path": str(voice),
            "provider": {
                "kind": "external",
                "api_key": "PRIVATE-KEY",
                "base_url": "https://example.com/v1",
                "model": "test",
            },
        },
    )
    assert response.status_code == 200
    id = response.json()["id"]
    assert "PRIVATE-KEY" not in (tmp_path / "jobs" / id / "request.json").read_text()
    saved = json.loads((tmp_path / "jobs" / id / "request.json").read_text())
    voice.unlink()
    assert Path(saved["voice_path"]).read_bytes() == b"placeholder"
    assert client.get(f"/artifacts/{id}/request.json").status_code == 404
    assert client.get("/api/jobs/../../etc").status_code == 404
    assert client.get("/").status_code == 200


def test_interrupted_jobs_are_recoverable_and_completed_jobs_cannot_restart(
    tmp_path, monkeypatch
):
    from knowledge_video.jobs import Jobs
    from knowledge_video.runtime import atomic_json

    id = "a" * 32
    p = tmp_path / "jobs" / id
    p.mkdir(parents=True)
    atomic_json(
        p / "status.json", {"id": id, "created": 1, "status": "running", "events": []}
    )
    jobs = Jobs(tmp_path)
    assert jobs.get(id)["status"] == "interrupted"
    atomic_json(
        p / "status.json", {"id": id, "created": 1, "status": "completed", "events": []}
    )
    with pytest.raises(ValueError, match="完成"):
        jobs.start(id)
    jobs.pool.shutdown(wait=True)


def test_external_provider_real_http_contract(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(
                (
                    self.path,
                    self.headers.get("Authorization"),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            body = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "title": "均值",
                                        "learning_goal": "理解均值",
                                        "outline": ["例子"],
                                        "candidate_urls": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        c = ProviderConfig(
            kind="external",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="fixture",
            api_key="test-token",
        )
        result = Provider(c, tmp_path).generate("test", {"topic": "均值"}, ResearchPlan)
        assert result.title == "均值"
        assert (
            captured[0][0] == "/v1/chat/completions"
            and captured[0][1] == "Bearer test-token"
        )
        assert captured[0][2]["response_format"] == {"type": "json_object"}
    finally:
        server.shutdown()
        server.server_close()


def test_codex_provider_passes_prompt_via_stdin_and_never_uses_shell(
    tmp_path, monkeypatch
):
    import knowledge_video.providers as module

    monkeypatch.setattr(module.shutil, "which", lambda x: "/codex")
    calls = []

    def run(args, cwd, cancel, timeout, stdin, log):
        calls.append((args, stdin))
        out = Path(args[args.index("--output-last-message") + 1])
        out.write_text(
            json.dumps(
                {
                    "title": "test",
                    "learning_goal": "goal",
                    "outline": [],
                    "candidate_urls": [],
                }
            )
        )

    monkeypatch.setattr(module, "run_process", run)
    Provider(ProviderConfig(), tmp_path).generate(
        "Only JSON", {"topic": "$(touch /tmp/bad)"}, ResearchPlan
    )
    args, prompt = calls[0]
    assert "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
    assert "--model" not in args and "$(touch /tmp/bad)" in prompt


def test_cancel_terminates_owned_child_process(tmp_path):
    import sys
    from knowledge_video.runtime import run_process, Cancelled

    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    with pytest.raises(Cancelled):
        run_process(
            [sys.executable, "-c", "import time;time.sleep(20)"], tmp_path, cancel, 5
        )
