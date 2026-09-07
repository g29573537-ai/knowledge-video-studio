from __future__ import annotations

import html
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import probe, run, write_json


def render_deck(cfg, timeline):
    plan = {
        "deck": str(cfg["deck_path"]),
        "output": str(cfg["build"] / "slides"),
        "width": cfg.get("width", 1920),
        "height": cfg.get("height", 1080),
        "chrome": cfg.get("chrome")
        or os.environ.get("CHROME_BIN")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "layoutReport": str(cfg["build"] / "layout_report.json"),
        "states": [timeline["initial_state"]]
        + [e["state"] for e in timeline["events"]],
    }
    target = cfg["build"] / "render_plan.json"
    write_json(target, plan)
    run(["node", Path(__file__).parent / "render_deck.mjs", target])
    return [Path(plan["output"]) / f"{i:04}.png" for i in range(len(plan["states"]))]


def font_for(cfg):
    size = int(cfg.get("subtitle", {}).get("font_size", 42))
    paths = [
        cfg.get("subtitle", {}).get("font"),
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in paths:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    raise ValueError(
        "No CJK subtitle font. Set subtitle.font to an installed font path"
    )


def visual_intervals(timeline):
    bounds = {0.0, timeline["duration"]}
    bounds.update(e["time"] for e in timeline["events"])
    for s in timeline["subtitles"]:
        bounds.update([s["start"], s["end"]])
    times = sorted(t for t in bounds if 0 <= t <= timeline["duration"])
    intervals = []
    for start, end in zip(times, times[1:]):
        middle = (start + end) / 2
        frame = 0
        for i, e in enumerate(timeline["events"], 1):
            if e["time"] <= middle:
                frame = i
        subtitle = next(
            (
                s["text"]
                for s in timeline["subtitles"]
                if s["start"] <= middle < s["end"]
            ),
            "",
        )
        if (
            intervals
            and intervals[-1]["frame"] == frame
            and intervals[-1]["text"] == subtitle
        ):
            intervals[-1]["end"] = end
        else:
            intervals.append(
                {"start": start, "end": end, "frame": frame, "text": subtitle}
            )
    return intervals


def export_video(cfg, timeline, slides):
    target = cfg["build"] / "video.mp4"
    frames = cfg["build"] / "composite"
    frames.mkdir(exist_ok=True)
    font = font_for(cfg)
    width, height = cfg.get("width", 1920), cfg.get("height", 1080)
    intervals = visual_intervals(timeline)
    lines = ["ffconcat version 1.0"]
    for i, interval in enumerate(intervals):
        image = Image.open(slides[interval["frame"]]).convert("RGB")
        if image.size != (width, height):
            raise ValueError("Slide renderer returned unexpected dimensions")
        if interval["text"]:
            draw = ImageDraw.Draw(image)
            text = interval["text"]
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if tw > width - 100:
                raise ValueError(
                    f"Subtitle too wide; reduce subtitle.max_chars: {text}"
                )
            y = height - cfg.get("subtitle", {}).get("bottom", 42) - th - 22
            x = (width - tw) / 2
            draw.rounded_rectangle(
                (x - 25, y - 16, x + tw + 25, y + th + 18), radius=10, fill="#111111"
            )
            draw.text(
                (x - bbox[0], y - bbox[1]),
                text,
                font=font,
                fill="white",
                stroke_width=1,
            )
        out = frames / f"{i:05}.png"
        image.save(out)
        # Paths are fixed numeric basenames relative to the concat file (safe even if root has quotes).
        lines.extend(
            [
                f"file '{out.name}'",
                f"duration {interval['end'] - interval['start']:.9f}",
            ]
        )
    lines.append(f"file '{len(intervals) - 1:05}.png'")
    concat = frames / "frames.ffconcat"
    concat.write_text("\n".join(lines) + "\n")
    tmp = target.with_suffix(".partial.mp4")
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat,
            "-i",
            cfg["build"] / "narration.wav",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{timeline['duration']:.9f}",
            "-r",
            str(cfg.get("fps", 30)),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            tmp,
        ]
    )
    info = probe(tmp)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    if (
        abs(float(info["format"]["duration"]) - timeline["duration"])
        > 2 / cfg.get("fps", 30) + 0.03
    ):
        raise ValueError("Export duration deviates from the narration clock")
    if abs(float(audio.get("duration", 0)) - timeline["duration"]) > 0.1:
        raise ValueError("Export truncated narration")
    tmp.replace(target)
    write_json(
        cfg["build"] / "export_report.json",
        {
            "video": str(target),
            "duration": float(info["format"]["duration"]),
            "narration_duration": timeline["duration"],
            "width": video["width"],
            "height": video["height"],
            "fps": video["r_frame_rate"],
            "audio_codec": audio["codec_name"],
            "visual_intervals": len(intervals),
            "cues": len(timeline["events"]),
            "subtitle_mode": "forced_alignment",
            "review_status": "needs_human_listening_review",
        },
    )
    return target


def write_review(cfg, timeline):
    # The iframe and audio are ordinary relative URLs; serve the project directory over localhost.
    deck = os.path.relpath(cfg["deck_path"], cfg["build"])
    payload = json.dumps(timeline, ensure_ascii=False).replace("<", "\\u003c")
    title = html.escape(cfg.get("title", "Narration review"))
    notice = html.escape(cfg.get("notice", "音频为主时间轴 · 点击标记可跳转试听"))
    page = r"""<!doctype html><html lang="zh"><meta charset="utf-8"><title>__TITLE__</title>
<style>body{margin:0;background:#151719;color:#eceeed;font:16px system-ui;padding:24px}main{max-width:1100px;margin:auto}h1{font-size:22px}p{color:#afb6bd}iframe{width:100%;aspect-ratio:__RATIO__;border:1px solid #41484e;background:#151719}audio{width:100%;margin-top:14px}#sub{min-height:32px;text-align:center;padding:12px}button{background:#242b31;color:inherit;border:1px solid #515b65;padding:8px 12px;margin:4px;border-radius:5px;cursor:pointer}#status{color:#95c7ec;font-size:14px}</style>
<main><h1>__TITLE__</h1><p>__NOTICE__</p>
<iframe id="deck" src="__DECK__"></iframe><audio id="audio" controls src="narration.wav"></audio><div id="sub"></div><div id="status"></div><div id="cues"></div></main>
<script>const timeline=__DATA__,a=document.querySelector('#audio'),frame=document.querySelector('#deck');let applied='';
function apply(state){const win=frame.contentWindow;if(win.setPresentationState)win.setPresentationState(state);else if(win.Reveal){win.Reveal.slide(state.h,state.v||0,state.f??-1);win.Reveal.layout();}else throw Error('Deck adapter not ready');}
function update(){const clock=a.currentTime+1e-6;let current={id:'initial',state:timeline.initial_state};for(const e of timeline.events)if(e.time<=clock)current=e;
if(applied!==current.id){try{apply(current.state);applied=current.id}catch(e){document.querySelector('#status').textContent=e.message;return}}
document.querySelector('#sub').textContent=(timeline.subtitles.find(s=>s.start<=clock&&clock<s.end)||{}).text||'';
document.querySelector('#status').textContent=`${a.currentTime.toFixed(2)} / ${timeline.duration.toFixed(2)} 秒 · ${current.id}`;}
for(const e of timeline.events){const b=document.createElement('button');b.textContent=`${e.time.toFixed(2)}s · ${e.id}`;b.onclick=()=>{a.currentTime=e.time;update()};document.querySelector('#cues').append(b)}
frame.onload=()=>{applied='';update()};a.addEventListener('seeked',update);function tick(){update();requestAnimationFrame(tick)}tick();</script></html>"""
    page = (
        page.replace("__TITLE__", title)
        .replace("__NOTICE__", notice)
        .replace("__RATIO__", f"{cfg.get('width', 1920)}/{cfg.get('height', 1080)}")
        .replace("__DECK__", html.escape(deck, quote=True))
        .replace("__DATA__", payload)
    )
    (cfg["build"] / "review.html").write_text(page, encoding="utf-8")
