from __future__ import annotations

from pathlib import Path
from typing import Any

from .protocol import AssetResult, ImageRequest, VideoRequest

_IMAGE_PROVIDERS: dict[str, Any] = {}
_VIDEO_PROVIDERS: dict[str, Any] = {}
_IMAGE_MODELS: dict[str, set[str]] = {}
_VIDEO_MODELS: dict[str, set[str]] = {}


def register_image_provider(
    name: str, provider: Any, models: set[str] | None = None
) -> None:
    _IMAGE_PROVIDERS[name] = provider
    _IMAGE_MODELS[name] = set(models or set())


def register_video_provider(
    name: str, provider: Any, models: set[str] | None = None
) -> None:
    _VIDEO_PROVIDERS[name] = provider
    _VIDEO_MODELS[name] = set(models or set())


def _resolve(
    name: str | None,
    registry: dict[str, Any],
    models: dict[str, set[str]],
    requested_model: str | None,
):
    if name is None:
        if not registry:
            raise ValueError("no image/video providers registered")
        name = next(iter(registry))
    if name not in registry:
        raise ValueError(f"unknown provider: {name}")
    if requested_model and models.get(name) and requested_model not in models[name]:
        raise ValueError(
            f"model {requested_model!r} is not allowed for provider {name!r}"
        )
    return name


def get_image_provider(name: str | None = None, model: str | None = None):
    resolved = _resolve(name, _IMAGE_PROVIDERS, _IMAGE_MODELS, model)
    return resolved, _IMAGE_PROVIDERS[resolved]


def get_video_provider(name: str | None = None, model: str | None = None):
    resolved = _resolve(name, _VIDEO_PROVIDERS, _VIDEO_MODELS, model)
    return resolved, _VIDEO_PROVIDERS[resolved]


def generate_image(
    request: ImageRequest,
    provider: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    allow_network: bool = False,
) -> AssetResult:
    provider_name, impl = get_image_provider(provider, model)
    if timeout is not None:
        request.timeout = timeout
    if not allow_network and getattr(impl, "requires_network", False):
        raise RuntimeError(
            f"provider {provider_name} requires network and allow_network is false"
        )
    result = impl.generate_image(request)
    if not result.sha256:
        from narration_video.core import file_hash

        p = Path(result.path)
        if p.exists():
            result.sha256 = file_hash(p)
    return result


def generate_video(
    request: VideoRequest,
    provider: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    allow_network: bool = False,
) -> AssetResult:
    provider_name, impl = get_video_provider(provider, model)
    if timeout is not None:
        request.timeout = timeout
    if not allow_network and getattr(impl, "requires_network", False):
        raise RuntimeError(
            f"provider {provider_name} requires network and allow_network is false"
        )
    result = impl.generate_video(request)
    if not result.sha256:
        from narration_video.core import file_hash

        p = Path(result.path)
        if p.exists():
            result.sha256 = file_hash(p)
    return result
