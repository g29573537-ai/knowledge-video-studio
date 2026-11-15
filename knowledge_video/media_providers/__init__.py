"""Independent image/video provider routing for Knowledge Video Studio.

This package is deliberately not derived from DrGekoz/Split-Node-YouTube.  Only the
architectural idea (one entry point, runtime backend/model selection) is used;
all code, names, tests and behaviour are implemented independently.
"""

from . import bootstrap  # noqa: F401
from .fake import FakeImageProvider
from .kaggle_voice import KaggleVoice
from .kokoro_voice import KokoroVoice
from .local import LocalProceduralImageProvider
from .protocol import AssetResult, ImageRequest, VideoRequest
from .registry import (
    generate_image,
    generate_video,
    get_image_provider,
    get_video_provider,
    register_image_provider,
    register_video_provider,
)

__all__ = [
    "AssetResult",
    "FakeImageProvider",
    "ImageRequest",
    "KaggleVoice",
    "KokoroVoice",
    "LocalProceduralImageProvider",
    "VideoRequest",
    "generate_image",
    "generate_video",
    "get_image_provider",
    "get_video_provider",
    "register_image_provider",
    "register_video_provider",
]
