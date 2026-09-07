from __future__ import annotations

import re

from .core import normalized


def subtitle_spans(text: str, max_chars: int = 24, chars=None):
    """Display original punctuation; anchor endpoints to scored spoken characters."""
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("subtitle.max_chars must be a positive integer")
    if chars is not None:
        return acoustic_subtitle_spans(text, max_chars, chars)
    pieces = re.findall(r"[^。！？；，]+[。！？；，]?", text)
    spans = []
    cursor = 0
    for piece in pieces:
        while piece:
            chunk, piece = piece[:max_chars], piece[max_chars:]
            length = len(normalized(chunk))
            if length:
                spans.append((chunk.strip(), cursor, cursor + length - 1))
            cursor += length
    return spans


def acoustic_subtitle_spans(text, max_chars, chars):
    """Choose line breaks at scored characters, retaining every original character.

    A weak character may remain inside a caption (subject to the block coverage
    gate), but must never supply its timestamp. No interpolation or dropped text.
    """
    prefix = [0]
    for character in text:
        prefix.append(prefix[-1] + len(normalized(character)))
    if prefix[-1] != len(chars):
        raise ValueError("Subtitle text and acoustic characters differ")
    size = len(text)
    pauses = {
        i
        for i in range(1, len(chars))
        if chars[i - 1].get("valid")
        and chars[i].get("valid")
        and isinstance(chars[i - 1].get("end"), (int, float))
        and isinstance(chars[i].get("start"), (int, float))
        and chars[i]["start"] - chars[i - 1]["end"] > 0.65
    }
    best = {size: (0.0, [])}
    punctuation = "。！？；，,.!?;:："
    for start in range(size - 1, -1, -1):
        choices = []
        for end in range(start + 1, min(size, start + max_chars) + 1):
            if end not in best or prefix[end] == prefix[start]:
                continue
            # Attach punctuation and spaces to the preceding caption.
            if end < size and not normalized(text[end]):
                continue
            first, last = prefix[start], prefix[end] - 1
            if any(first < pause <= last for pause in pauses):
                continue
            if not chars[first]["valid"] or not chars[last]["valid"]:
                continue
            length = end - start
            boundary_penalty = 0 if text[end - 1] in punctuation or end == size else 8
            short_penalty = max(0, 7 - length) * 3
            score = (
                best[end][0]
                + 4
                + boundary_penalty
                + short_penalty
                + ((max_chars - length) / max_chars) ** 2
            )
            choices.append(
                (score, [(text[start:end].strip(), first, last)] + best[end][1])
            )
        if choices:
            best[start] = min(choices, key=lambda item: item[0])
    if 0 not in best:
        raise ValueError(
            "No reliable subtitle boundaries within max_chars; review/re-record narration"
        )
    return best[0][1]


def compile_timeline(blocks, cue_states, cfg):
    events, subtitles = [], []
    min_score = cfg.get("alignment", {}).get("min_cue_score", 0.15)
    for block in blocks:
        chars = block["chars"]
        offset = block["offset"]
        for cue in block["cues"]:
            token = chars[cue["char_index"]]
            if not token["valid"] or token["score"] < min_score:
                raise ValueError(
                    f"Cue {cue['id']} lacks reliable acoustic timing; re-record or move marker"
                )
            state = cue_states[cue["id"]]
            lead = float(state.get("lead_seconds", 0))
            if not 0 <= lead <= 1:
                raise ValueError("Cue lead_seconds must be between 0 and 1")
            events.append(
                {
                    "id": cue["id"],
                    "block": block["id"],
                    "time": max(0, offset + token["start"] - lead),
                    "spoken_time": offset + token["start"],
                    "score": token["score"],
                    "state": {k: v for k, v in state.items() if k != "lead_seconds"},
                }
            )
        for text, first, last in subtitle_spans(
            block["text"], cfg.get("subtitle", {}).get("max_chars", 24), chars
        ):
            left, right = chars[first], chars[last]
            if not left["valid"] or not right["valid"]:
                raise ValueError(
                    f"Subtitle boundary in {block['id']} lacks reliable alignment: {text}"
                )
            subtitles.append(
                {
                    "text": text,
                    "start": offset + left["start"],
                    "end": offset + right["end"],
                }
            )
    if not events:
        raise ValueError("No visual events")
    for a, b in zip(events, events[1:]):
        if b["time"] <= a["time"]:
            raise ValueError(f"Cues collide or reverse: {a['id']}, {b['id']}")
    for a, b in zip(subtitles, subtitles[1:]):
        # CTC rounding can overlap adjacent boundaries by one acoustic frame.
        if a["end"] > b["start"]:
            if a["end"] - b["start"] > 0.05:
                raise ValueError("Overlapping subtitle alignment")
            a["end"] = b["start"]
    return {
        "schema": 1,
        "clock": "narration_audio",
        "duration": cfg["duration"],
        "initial_state": events[0]["state"],
        "events": events,
        "subtitles": subtitles,
        "blocks": [
            {k: b[k] for k in ["id", "offset", "duration", "coverage"]} for b in blocks
        ],
    }


def timestamp(value):
    ms = round(value * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(timeline):
    return (
        "\n\n".join(
            f"{i}\n{timestamp(s['start'])} --> {timestamp(s['end'])}\n{s['text']}"
            for i, s in enumerate(timeline["subtitles"], 1)
        )
        + "\n"
    )
