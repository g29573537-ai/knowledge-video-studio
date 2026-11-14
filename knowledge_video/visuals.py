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
