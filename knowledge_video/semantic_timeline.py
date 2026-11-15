"""Semantic timeline layer for Knowledge Video Studio.

This layer sits beside ``narration_video.timeline.compile_timeline``.  The low-level
timeline owns acoustic seconds; this module owns meaning: scene -> beat -> event,
with every phrase anchored to real character timings from forced alignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "semantic_timeline"
SEMANTIC_VERSION = 1


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _get(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def normalized(text: str) -> str:
    return "".join(c.lower() for c in str(text) if c.isalnum())


def _normalized_positions(text: str) -> list[int]:
    return [i for i, c in enumerate(text) if normalized(c)]


def _original_slice(text: str, start_norm: int, end_norm: int) -> str:
    positions = _normalized_positions(text)
    if not positions or start_norm >= len(positions):
        return ""
    start = positions[max(0, start_norm)]
    end_index = min(len(positions) - 1, max(start_norm, end_norm))
    end = positions[end_index]
    return text[start : end + 1]


def resolve_anchor(
    phrase: str,
    text: str,
    chars: list[dict] | None = None,
    offset: float = 0.0,
) -> dict[str, Any]:
    """Resolve a spoken phrase to normalized character and acoustic time anchors."""

    needle = normalized(phrase)
    haystack = normalized(text)
    if not needle:
        raise ValueError("Semantic anchor phrase must not be empty")
    position = haystack.find(needle)
    if position < 0:
        raise ValueError(f"Unresolved semantic anchor: {phrase!r}")
    start = position
    end = position + len(needle) - 1
    result = {
        "phrase": phrase,
        "anchor_text": phrase,
        "char_start": start,
        "char_end": end,
        "word_start": start,
        "word_end": end,
        "time_start": None,
        "time_end": None,
    }
    if chars is not None:
        if start >= len(chars) or end >= len(chars):
            raise ValueError(f"Semantic anchor outside acoustic timing: {phrase!r}")
        if not bool(chars[start].get("valid", False)) or not bool(
            chars[end].get("valid", False)
        ):
            raise ValueError(
                f"Semantic anchor lacks reliable acoustic timing: {phrase!r}"
            )
        result["time_start"] = offset + float(chars[start].get("start", 0.0))
        result["time_end"] = offset + float(
            chars[end].get("end", chars[end].get("start", 0.0))
        )
    return result


@dataclass
class MediaSource:
    type: str = "unknown"
    asset_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "asset_ref": self.asset_ref}


@dataclass
class CameraPlan:
    view: str = "overview"
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"view": self.view}
        if self.kind is not None:
            result["kind"] = self.kind
        return result


@dataclass
class ActionWindow:
    start: float | None = None
    end: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end}


@dataclass
class SemanticBeat:
    id: str
    cue_id: str | None = None
    phrase: str = ""
    anchor_text: str = ""
    visual_object: str | None = None
    fact_claim_id: str | None = None
    media_source: MediaSource = field(default_factory=MediaSource)
    asset_ref: str | None = None
    camera_plan: list[CameraPlan] = field(default_factory=lambda: [CameraPlan()])
    action_window: ActionWindow = field(default_factory=ActionWindow)
    word_start: int = 0
    word_end: int = 0
    char_start: int = 0
    char_end: int = 0
    time_start: float | None = None
    time_end: float | None = None
    semantic_version: int = SEMANTIC_VERSION
    visual_role: str = "hero"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cue_id": self.cue_id,
            "phrase": self.phrase,
            "anchor_text": self.anchor_text,
            "visual_object": self.visual_object,
            "fact_claim_id": self.fact_claim_id,
            "media_source": self.media_source.to_dict(),
            "asset_ref": self.asset_ref,
            "camera_plan": [c.to_dict() for c in self.camera_plan],
            "action_window": self.action_window.to_dict(),
            "word_start": self.word_start,
            "word_end": self.word_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "semantic_version": self.semantic_version,
            "visual_role": self.visual_role,
        }


@dataclass
class SemanticEvent:
    id: str
    beat_id: str | None = None
    time: float | None = None
    spoken_time: float | None = None
    score: float | None = None
    state: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "beat_id": self.beat_id,
            "time": self.time,
            "spoken_time": self.spoken_time,
            "score": self.score,
            "state": self.state,
        }


@dataclass
class SemanticScene:
    id: str
    block_id: str | None = None
    slide_id: str | None = None
    headline: str | None = None
    narration: str = ""
    visual_role: str = "hero"
    beats: list[SemanticBeat] = field(default_factory=list)
    events: list[SemanticEvent] = field(default_factory=list)
    semantic_version: int = SEMANTIC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "block_id": self.block_id,
            "slide_id": self.slide_id,
            "headline": self.headline,
            "narration": self.narration,
            "visual_role": self.visual_role,
            "beats": [b.to_dict() for b in self.beats],
            "events": [e.to_dict() for e in self.events],
            "semantic_version": self.semantic_version,
        }


@dataclass
class SemanticTimeline:
    scenes: list[SemanticScene] = field(default_factory=list)
    semantic_version: int = SEMANTIC_VERSION
    schema: str = SCHEMA
    schema_version: int = SEMANTIC_VERSION
    version: int = SEMANTIC_VERSION

    def to_dict(self) -> dict[str, Any]:
        beats = [b for scene in self.scenes for b in scene.beats]
        events = [e for scene in self.scenes for e in scene.events]
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "semantic_version": self.semantic_version,
            "version": self.version,
            "scenes": [s.to_dict() for s in self.scenes],
            "beats": [b.to_dict() for b in beats],
            "events": [e.to_dict() for e in events],
        }


def _merge_blocks(blocks: Any, aligned_blocks: Any = None) -> list[dict[str, Any]]:
    block_list = [_as_dict(b) for b in (blocks or [])]
    aligned_list = [_as_dict(b) for b in (aligned_blocks or [])]
    if not aligned_list:
        return block_list
    by_id = {_get(b, "id"): b for b in aligned_list if _get(b, "id") is not None}
    merged = []
    for block in block_list:
        bid = _get(block, "id")
        aligned = by_id.get(bid, {})
        merged.append({**block, **aligned})
    if not block_list and aligned_list:
        merged = aligned_list
    return merged


def _cue_list(block: dict[str, Any]) -> list[dict[str, Any]]:
    cues = _get(block, "cues", []) or []
    return sorted(
        [_as_dict(c) for c in cues], key=lambda c: int(c.get("char_index", 0))
    )


def _event_time_map(timeline: Any) -> dict[str, float]:
    result: dict[str, Any] = {}
    if not timeline:
        return result
    data = _as_dict(timeline)
    for event in data.get("events", []) or []:
        event = _as_dict(event)
        if event.get("id") is not None and event.get("time") is not None:
            result[str(event["id"])] = float(event["time"])
    return result


def build_semantic_timeline(
    blocks: Any = None,
    aligned_blocks: Any = None,
    alignments: Any = None,
    timeline: Any = None,
    cfg: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if blocks is None:
        blocks = kwargs.get("blocks")
    if aligned_blocks is None:
        aligned_blocks = (
            kwargs.get("aligned_blocks") or kwargs.get("aligned") or alignments
        )
    merged_blocks = _merge_blocks(blocks, aligned_blocks)
    if not merged_blocks and aligned_blocks is not None:
        merged_blocks = [_as_dict(b) for b in aligned_blocks]
    event_times = _event_time_map(timeline)
    scenes: list[SemanticScene] = []
    for block in merged_blocks:
        block = _as_dict(block)
        block_id = str(_get(block, "id", _get(block, "block_id", "scene")))
        narration = str(_get(block, "narration", _get(block, "text", "")))
        chars = _get(block, "chars")
        offset = float(_get(block, "offset", 0.0) or 0.0)
        duration = _get(block, "duration")
        cues = _cue_list(block)
        cues_or_none = cues
        normalized_length = len(normalized(narration))
        if not cues_or_none:
            cues_or_none = [{"id": f"{block_id}-beat", "char_index": 0}]
        beats: list[SemanticBeat] = []
        events: list[SemanticEvent] = []
        for index, cue in enumerate(cues_or_none):
            cue_id = _get(cue, "id")
            start_char = int(_get(cue, "char_index", 0) or 0)
            if index + 1 < len(cues_or_none):
                end_char = int(
                    _get(cues_or_none[index + 1], "char_index", start_char + 1)
                    or start_char + 1
                )
            else:
                end_char = normalized_length
            if end_char <= start_char:
                end_char = min(normalized_length, start_char + 1)
            phrase = _original_slice(narration, start_char, end_char - 1).strip()
            if not phrase:
                phrase = narration.strip()
            anchor = resolve_anchor(phrase, narration, chars, offset)
            if cue_id is not None and str(cue_id) in event_times:
                time_start = event_times[str(cue_id)]
            else:
                time_start = anchor["time_start"]
            if (
                index + 1 < len(cues_or_none)
                and str(_get(cues_or_none[index + 1], "id")) in event_times
            ):
                time_end = event_times[str(_get(cues_or_none[index + 1], "id"))]
            elif duration is not None:
                time_end = offset + float(duration)
            else:
                time_end = anchor["time_end"]
            media_source_raw = _get(block, "media_source", None)
            if isinstance(media_source_raw, str):
                media_source_raw = {
                    "type": media_source_raw,
                    "asset_ref": _get(block, "asset_ref"),
                }
            media_source = MediaSource(
                type=str(
                    _get(
                        media_source_raw,
                        "type",
                        _get(
                            block, "media_source_type", _get(block, "media", "unknown")
                        ),
                    )
                ),
                asset_ref=_get(media_source_raw, "asset_ref", _get(block, "asset_ref")),
            )
            camera_raw = _get(block, "camera_plan", None)
            if camera_raw is None:
                camera_raw = [
                    {
                        "view": _get(
                            block, "camera_view", _get(block, "camera", "overview")
                        )
                    }
                ]
            camera_plan = [
                CameraPlan(
                    view=str(_get(c, "view", _get(c, "kind", "overview"))),
                    kind=_get(c, "kind"),
                )
                for c in [_as_dict(x) for x in camera_raw]
            ] or [CameraPlan()]
            # Manifest explicitly separates camera.view from shot kind; keep view as the
            # camera field and do not overwrite it with source kind.
            if all(c.kind is not None and c.view == "overview" for c in camera_plan):
                pass
            visual_object = _get(
                block,
                "visual_object",
                _get(block, "visual", _get(block, "headline", _get(block, "slide_id"))),
            )
            fact_claim_id = _get(block, "fact_claim_id", None)
            if fact_claim_id is None:
                source_ids = _get(block, "source_ids", []) or []
                fact_claim_id = source_ids[0] if source_ids else block_id
            action_window: Any = _get(block, "action_window", None)
            if action_window is None:
                action_window = {"start": time_start, "end": time_end}
            else:
                action_window = _as_dict(action_window)
                action_window.setdefault("start", time_start)
                action_window.setdefault("end", time_end)
            beat = SemanticBeat(
                id=f"{block_id}:{cue_id}",
                cue_id=str(cue_id) if cue_id is not None else None,
                phrase=phrase,
                anchor_text=str(_get(block, "anchor_text", phrase) or phrase),
                visual_object=visual_object,
                fact_claim_id=fact_claim_id,
                media_source=media_source,
                asset_ref=media_source.asset_ref,
                camera_plan=camera_plan,
                action_window=ActionWindow(
                    start=action_window.get("start"), end=action_window.get("end")
                ),
                word_start=anchor["word_start"],
                word_end=anchor["word_end"],
                char_start=anchor["char_start"],
                char_end=anchor["char_end"],
                time_start=time_start,
                time_end=time_end,
                semantic_version=SEMANTIC_VERSION,
                visual_role=str(_get(block, "visual_role", "hero")),
            )
            beats.append(beat)
            if cue_id is not None:
                events.append(
                    SemanticEvent(
                        id=str(cue_id),
                        beat_id=beat.id,
                        time=time_start,
                        spoken_time=anchor["time_start"]
                        if anchor["time_start"] is not None
                        else time_start,
                        score=_get(
                            next((c for c in chars or [] if False), {}), "score", None
                        ),
                        state={"slide": _get(block, "slide_id")},
                    )
                )
        # Score lookup for cue char.
        for event in events:
            pass
        # Attach cue scores where possible.
        cue_by_id = {str(_get(c, "id")): c for c in cues}
        for event in events:
            cue_item: Any = cue_by_id.get(event.id)
            if cue_item is not None and chars is not None:
                ci = int(cue_item.get("char_index", 0) or 0)
                if 0 <= ci < len(chars):
                    event.score = chars[ci].get("score")
        scene = SemanticScene(
            id=block_id,
            block_id=block_id,
            slide_id=_get(block, "slide_id"),
            headline=_get(block, "headline"),
            narration=narration,
            visual_role=str(_get(block, "visual_role", "hero")),
            beats=beats,
            events=events,
            semantic_version=SEMANTIC_VERSION,
        )
        scenes.append(scene)
    return SemanticTimeline(scenes=scenes).to_dict()


def validate_semantic_timeline(timeline: Any) -> bool:
    data = _as_dict(timeline)
    scenes = data.get("scenes", data.get("blocks", []))
    for scene in scenes or []:
        scene = _as_dict(scene)
        beats = scene.get("beats", [])
        for beat in beats or []:
            beat = _as_dict(beat)
            if beat.get("char_start") is None or beat.get("char_end") is None:
                raise ValueError("Semantic timeline contains an unresolved anchor")
            if int(beat.get("char_end", -1)) < int(beat.get("char_start", 0)):
                raise ValueError("Semantic timeline contains an unresolved anchor")
            phrase = beat.get("phrase")
            if not phrase:
                raise ValueError("Semantic timeline contains an empty phrase")
            media_source = _as_dict(beat.get("media_source"))
            if "type" not in media_source:
                raise ValueError("media_source.type is required")
            camera_plan = beat.get("camera_plan") or []
            for camera in camera_plan:
                camera = _as_dict(camera)
                if "view" not in camera:
                    raise ValueError("camera.view is required")
    return True


def ensure_anchors(timeline: Any) -> bool:
    return validate_semantic_timeline(timeline)


# Compatibility aliases.
compile_semantic_timeline = build_semantic_timeline
build_timeline = build_semantic_timeline
SemanticTimelineV1 = SemanticTimeline
