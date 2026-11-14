from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AssetResult:
    path: str
    provider: str
    model: str = ""
    mime_type: str = "image/png"
    sha256: str = ""
    width: int = 0
    height: int = 0
    seed: int | None = None
    duration: float | None = None
    warnings: list[str] = field(default_factory=list)
    cost_estimate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageRequest:
    prompt: str
    output_path: str | Path
    width: int = 1024
    height: int = 1024
    seed: int | None = None
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoRequest:
    prompt: str
    output_path: str | Path
    width: int = 1920
    height: int = 1080
    duration: float = 3.0
    seed: int | None = None
    timeout: float = 120.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str

    def generate_image(self, request: ImageRequest) -> AssetResult: ...


class VideoProvider(Protocol):
    name: str

    def generate_video(self, request: VideoRequest) -> AssetResult: ...
