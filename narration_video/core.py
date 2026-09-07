from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def probe(path: Path) -> dict:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def normalized(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalnum())


def parse_script(text: str) -> list[dict]:
    """## block-id defines a natural paragraph; [[cue-id]] anchors its next word."""
    blocks = []
    block_id = None
    lines = []
    ids = set()
    cue_ids = set()

    def finish():
        if block_id is None:
            return
        raw = "".join(lines).strip()
        spoken = ""
        cues = []
        cursor = 0
        for match in re.finditer(r"\[\[([A-Za-z0-9_-]+)\]\]", raw):
            spoken += raw[cursor : match.start()]
            cue_id = match.group(1)
            if cue_id in cue_ids:
                raise ValueError(f"Duplicate cue: {cue_id}")
            cue_ids.add(cue_id)
            cues.append({"id": cue_id, "char_index": len(normalized(spoken))})
            cursor = match.end()
        spoken += raw[cursor:]
        if "[[" in spoken or "]]" in spoken:
            raise ValueError(f"Malformed cue in {block_id}")
        if not normalized(spoken):
            raise ValueError(f"Empty narration block: {block_id}")
        if len(spoken) > 4096:
            raise ValueError(
                f"Block {block_id} exceeds OmniVoice's 4096 character limit"
            )
        for cue in cues:
            if cue["char_index"] >= len(normalized(spoken)):
                raise ValueError(f"Cue {cue['id']} has no following spoken word")
        blocks.append({"id": block_id, "text": spoken, "cues": cues})

    for line in text.splitlines():
        if line.startswith("## "):
            finish()
            block_id = line[3:].strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]+", block_id) or block_id in ids:
                raise ValueError(f"Invalid or duplicate block id: {block_id}")
            ids.add(block_id)
            lines = []
        elif line.startswith("# ") or not line.strip():
            continue
        elif block_id is None:
            raise ValueError("Narration must appear below a ## block-id heading")
        else:
            lines.append(line.strip() + (" " if line.strip()[-1:].isascii() else ""))
    finish()
    if not blocks:
        raise ValueError("No narration blocks")
    return blocks


def load_project(path: Path) -> dict:
    path = path.resolve()
    cfg = read_json(path)
    cfg["root"] = path.parent
    cfg["config_path"] = path
    cfg["build"] = (path.parent / cfg.get("build_dir", "build")).resolve()
    cfg["script_path"] = (path.parent / cfg["script"]).resolve()
    cfg["deck_path"] = (path.parent / cfg["deck"]).resolve()
    cfg["blocks"] = parse_script(cfg["script_path"].read_text(encoding="utf-8"))
    declared = {cue["id"] for b in cfg["blocks"] for cue in b["cues"]}
    states = set(cfg["cues"])
    if declared != states:
        raise ValueError(
            f"Cue mapping differs: missing={declared - states}, unused={states - declared}"
        )
    if not declared:
        raise ValueError("At least one visual cue is required")
    if not cfg["deck_path"].is_file():
        raise ValueError(f"Missing deck: {cfg['deck_path']}")
    for key in ("width", "height"):
        value = cfg.get(key, 1920 if key == "width" else 1080)
        if not isinstance(value, int) or value < 240 or value % 2:
            raise ValueError(f"{key} must be an even integer >= 240")
    fps = cfg.get("fps", 30)
    if not isinstance(fps, int) or not 1 <= fps <= 60:
        raise ValueError("fps must be an integer between 1 and 60")
    pause = cfg.get("pause_between_blocks", 0.35)
    if (
        not isinstance(pause, (int, float))
        or not math.isfinite(pause)
        or pause < 0
        or pause > 10
    ):
        raise ValueError("pause_between_blocks must be between 0 and 10 seconds")
    speed = cfg.get("playback_speed", 1.0)
    if (
        not isinstance(speed, (int, float))
        or not math.isfinite(speed)
        or not 0.5 <= speed <= 2
    ):
        raise ValueError("playback_speed must be between 0.5 and 2")
    return cfg


def timing_spec(cfg):
    return digest(
        {
            "cues": cfg["cues"],
            "alignment": cfg.get("alignment", {}),
            "subtitle": cfg.get("subtitle", {}),
            "playback_speed": cfg.get("playback_speed", 1.0),
            "schema": 3,
        }
    )
