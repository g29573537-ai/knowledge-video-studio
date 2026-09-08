"""Actual browser regression for transition settling and clipped text."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from knowledge_video.workflow import chrome_path


def test_render_waits_for_animation_and_detects_parent_clipping(tmp_path):
    chrome = chrome_path()
    if not Path(chrome).is_file() or not shutil.which("node"):
        pytest.skip("Chrome and Node are required for slide rendering")
    deck = tmp_path / "slides.html"
    deck.write_text("""<!doctype html><html><head><style>
      body{margin:0;background:#191919;color:white;font:32px Arial}
      #viewport{position:absolute;left:100px;top:100px;width:700px;height:500px;overflow:hidden}
      section{display:none;width:700px;height:500px}section.active{display:block}
      #moving.active p{animation:enter .65s linear forwards}
      #clipped p{position:relative;left:620px;white-space:nowrap}
      @keyframes enter{from{transform:translateX(1000px)}to{transform:translateX(0)}}
    </style></head><body><div id="viewport"><section id="moving"><p>Settled title</p></section>
    <section id="clipped"><p>This text exceeds its parent container.</p></section></div>
    <script>window.setPresentationState=s=>document.querySelectorAll('section').forEach(e=>e.classList.toggle('active',e.id===s.slide));</script></body></html>""")
    report = tmp_path / "report.json"
    cfg = tmp_path / "render.json"
    cfg.write_text(
        json.dumps(
            {
                "deck": str(deck),
                "output": str(tmp_path / "frames"),
                "width": 1920,
                "height": 1080,
                "chrome": chrome,
                "states": [{"slide": "moving"}, {"slide": "clipped"}],
                "layoutReport": str(report),
            }
        )
    )
    renderer = Path(__file__).resolve().parents[1] / "narration_video/render_deck.mjs"
    subprocess.run(
        ["node", str(renderer), str(cfg)],
        check=True,
        capture_output=True,
        text=True,
        timeout=35,
    )
    pages = json.loads(report.read_text())
    assert pages[0]["issues"] == [], (
        "Capture must wait until the moving title is settled"
    )
    assert any(
        "text clipped by div#viewport" in i["problem"] for i in pages[1]["issues"]
    )
    assert len(list((tmp_path / "frames").glob("*.png"))) == 2


@pytest.mark.parametrize(
    "root_css,body_css,clipped",
    [
        ("", "", False),
        ("overflow:hidden;height:0", "overflow:visible", False),
        ("overflow:hidden", "position:relative;height:20px", True),
        ("", "contain:paint;height:20px", True),
    ],
)
def test_root_overflow_uses_viewport_but_local_body_clipping_remains(
    tmp_path, root_css, body_css, clipped
):
    chrome = chrome_path()
    if not Path(chrome).is_file() or not shutil.which("node"):
        pytest.skip("Chrome and Node are required for slide rendering")
    deck = tmp_path / "slides.html"
    deck.write_text("""<!doctype html><html><head><style>
      html{%s}body{margin:0;overflow:hidden;background:#191919;color:white;font:32px Arial;%s}
      section{position:absolute;left:100px;top:100px;width:700px;height:500px}
      #outside{position:absolute;top:1050px}
    </style></head><body><section id="slide"><p>Visible title inside the viewport</p>
    <p id="outside">Text beyond the viewport</p></section>
    <script>window.setPresentationState=()=>{};</script></body></html>""" % (root_css, body_css))
    report = tmp_path / "report.json"
    cfg = tmp_path / "render.json"
    cfg.write_text(json.dumps({
        "deck": str(deck), "output": str(tmp_path / "frames"),
        "width": 1920, "height": 1080, "chrome": chrome,
        "states": [{"slide": "slide"}], "layoutReport": str(report),
    }))
    renderer = Path(__file__).resolve().parents[1] / "narration_video/render_deck.mjs"
    subprocess.run(["node", str(renderer), str(cfg)], check=True,
                   capture_output=True, text=True, timeout=35)
    issues = json.loads(report.read_text())[0]["issues"]
    title_issues = [i for i in issues if i["text"].startswith("Visible title")]
    assert bool(title_issues) == clipped
    if clipped:
        assert all("clipped by body" in i["problem"] for i in title_issues)
    assert any(i["text"].startswith("Text beyond") for i in issues)
