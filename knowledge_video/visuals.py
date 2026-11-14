"""Visual selection policy for Knowledge Video Studio.

Procedural rendering is the default.  Diffusion/remote AI is an explicit option and
never activates implicitly just because weights or libraries are installed.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw

VisualMode = str


@dataclass
class VisualResult:
    output_path: str
    backend: str
    model: str = ""
    seed: int | None = None
    duration: float = 0.0
    warnings: list[str] = None
    cost_estimate: float | None = None
    fallback_used: bool = False
    cache_key: str = ""
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _render_procedural(prompt: str, output: Path, width: int = 1024, height: int = 1024, seed: int | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, width - 24, height - 24), outline="#60a5fa", width=4)
    draw.text((48, 48), (prompt or "procedural visual")[:120], fill="white")
    image.save(output)


def render_procedural(prompt: str, output: str | Path, width: int = 1024, height: int = 1024, seed: int | None = None) -> Path:
    output = Path(output)
    _render_procedural(prompt, output, width, height, seed)
    return output


def _diffusion_available(config: Any = None) -> bool:
    if config is not None and getattr(config, "diffusion_available_override", None) is not None:
        return bool(config.diffusion_available_override)
    return False


def _diffusion_model_present(config: Any = None) -> bool:
    return False


def _generate_with_diffusion(prompt: str, output: Path, seed: int | None = None, config: Any = None) -> Path:
    raise RuntimeError("local diffusion is not installed")


def _cache_key(prompt: str, mode: str, model: str, seed: int | None) -> str:
    return hashlib.sha256(
        json.dumps({"prompt": prompt, "mode": mode, "model": model, "seed": seed}, sort_keys=True).encode()
    ).hexdigest()


def generate_scene_visual(
    prompt: str = "",
    output: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    visual_mode: str = "procedural",
    ai_fallback_enabled: bool = False,
    scene_role: str = "hero",
    allowed_roles: list[str] | None = None,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    model: str = "",
    config: Any = None,
    diffusion_available: Callable[[], bool] | None = None,
    diffusion_model_present: Callable[[], bool] | None = None,
    generate_diffusion: Callable[[str, Path, int | None], Path] | None = None,
    timeout: float = 120.0,
) -> VisualResult:
    target = Path(output or output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed = allowed_roles if allowed_roles is not None else ["secondary", "bridge", "background"]
    role_allowed = scene_role in allowed or ai_fallback_enabled
    key = _cache_key(prompt, visual_mode, model, seed)
    sidecar = target.with_suffix(target.suffix + ".visual.json")
    if target.exists() and sidecar.exists():
        try:
            saved = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
        if saved.get("cache_key") == key:
            return VisualResult(
                output_path=str(target),
                backend=saved.get("backend", "procedural"),
                model=saved.get("model", model),
                seed=seed,
                duration=float(saved.get("duration", 0.0)),
                warnings=list(saved.get("warnings", [])),
                cost_estimate=saved.get("cost_estimate"),
                fallback_used=bool(saved.get("fallback_used", False)),
                cache_key=key,
                metadata=dict(saved.get("metadata", {})),
            )

    started = time.monotonic()
    warnings: list[str] = []
    fallback_used = False
    backend = "procedural"
    used_model = model

    if visual_mode == "procedural":
        _render_procedural(prompt, target, width, height, seed)
    elif visual_mode in {"local_diffusion", "remote_api"}:
        avail = diffusion_available() if diffusion_available is not None else _diffusion_available(config)
        present = diffusion_model_present() if diffusion_model_present is not None else _diffusion_model_present(config)
        if not (avail and present):
            if not role_allowed:
                raise RuntimeError("AI visual is not enabled for this scene")
            _render_procedural(prompt, target, width, height, seed)
            fallback_used = True
            warnings.append("AI backend unavailable; procedural fallback used")
        else:
            try:
                generator = generate_diffusion or _generate_with_diffusion
                generator(prompt, target, seed)
                backend = "local_diffusion" if visual_mode == "local_diffusion" else "remote_api"
                used_model = model or ("sdxl-turbo" if visual_mode == "local_diffusion" else "remote")
            except Exception as exc:
                if not role_allowed:
                    raise
                _render_procedural(prompt, target, width, height, seed)
                fallback_used = True
                backend = "procedural"
                warnings.append(f"AI visual failed; procedural fallback used: {exc}")
    else:
        raise ValueError(f"unknown visual_mode: {visual_mode}")

    duration = time.monotonic() - started
    result = VisualResult(
        output_path=str(target),
        backend=backend,
        model=used_model,
        seed=seed,
        duration=duration,
        warnings=warnings,
        cost_estimate=None,
        fallback_used=fallback_used,
        cache_key=key,
        metadata={"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
    )
    sidecar.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _beat_get(beat: Any, key: str, default: Any = None) -> Any:
    if isinstance(beat, dict):
        return beat.get(key, default)
    return getattr(beat, key, default)


def _beat_set(beat: Any, key: str, value: Any) -> None:
    if isinstance(beat, dict):
        beat[key] = value
    else:
        setattr(beat, key, value)


def _collect_beats(value: Any) -> list[Any]:
    if isinstance(value, dict):
        if "beats" in value:
            collected = []
            for scene in value.get("scenes", [value]):
                collected.extend(_collect_beats(scene))
            if value.get("beats"):
                collected.extend(value["beats"])
            return collected
        if "scenes" in value:
            collected = []
            for scene in value["scenes"]:
                collected.extend(_collect_beats(scene))
            return collected
    if isinstance(value, list):
        return list(value)
    beats = getattr(value, "beats", None)
    if beats is not None:
        return list(beats)
    return [value]


def auto_fill_secondary_visuals(
    beats_or_timeline: Any,
    *,
    registry: Any = None,
    visual_config: Any = None,
    output_dir: str | Path = ".",
    prompt_builder: Any = None,
    seed: int | None = None,
    width: int = 512,
    height: int = 512,
) -> list[Any]:
    """Generate visuals only for secondary/bridge/background beats."""

    from .media_rights import MediaRightsRegistry

    if registry is None:
        registry = MediaRightsRegistry()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    allowed_roles = getattr(visual_config, "allowed_roles", None)
    if allowed_roles is None and isinstance(visual_config, dict):
        allowed_roles = visual_config.get("allowed_roles", ["secondary", "bridge", "background"])
    if allowed_roles is None:
        allowed_roles = ["secondary", "bridge", "background"]
    visual_mode = getattr(visual_config, "visual_mode", None)
    if visual_mode is None and isinstance(visual_config, dict):
        visual_mode = visual_config.get("visual_mode", "procedural")
    if visual_mode is None:
        visual_mode = "procedural"
    ai_fallback_enabled = getattr(visual_config, "ai_fallback_enabled", False)
    if isinstance(visual_config, dict):
        ai_fallback_enabled = visual_config.get("ai_fallback_enabled", ai_fallback_enabled)

    results = []
    for beat in _collect_beats(beats_or_timeline):
        role = str(_beat_get(beat, "visual_role", "hero"))
        if role not in allowed_roles:
            results.append(None)
            continue
        beat_id = str(_beat_get(beat, "id", _beat_get(beat, "cue_id", "beat")))
        prompt = prompt_builder(beat) if callable(prompt_builder) else str(_beat_get(beat, "visual_object") or _beat_get(beat, "phrase") or beat_id)
        output = output_dir / f"{beat_id.replace(':', '_')}.png"
        result = generate_scene_visual(
            prompt,
            output=output,
            visual_mode=visual_mode,
            ai_fallback_enabled=ai_fallback_enabled,
            scene_role=role,
            allowed_roles=allowed_roles,
            width=width,
            height=height,
            seed=seed,
            config=visual_config,
        )
        _beat_set(beat, "asset_ref", output.name)
        media_source = _beat_get(beat, "media_source", None)
        if isinstance(media_source, dict):
            media_source["asset_ref"] = output.name
            media_source.setdefault("type", "generated")
            _beat_set(beat, "media_source", media_source)
        elif media_source is not None:
            setattr(media_source, "asset_ref", output.name)
        else:
            _beat_set(beat, "media_source", {"type": "generated", "asset_ref": output.name})

        from narration_video.core import file_hash

        registry.register_generated(
            asset_id=f"generated:{beat_id}",
            generation_provider=result.backend,
            model_id=result.model or result.backend,
            model_version="",
            weights_license_url="",
            provider_terms_url="",
            terms_checked_at="",
            prompt=prompt,
            prompt_sha256=result.metadata.get("prompt_sha256", ""),
            seed=seed,
            local_path=str(output),
            sha256=file_hash(output),
            size_bytes=output.stat().st_size,
            mime_type="image/png",
        )
        results.append(result)
    return results
