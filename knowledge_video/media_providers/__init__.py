"""Independent image/video provider routing for Knowledge Video Studio.

This package is deliberately not derived from DrGekoz/Split-Node-YouTube.  Only the
architectural idea (one entry point, runtime backend/model selection) is used;
all code, names, tests and behaviour are implemented independently.
"""

from .protocol import AssetResult, ImageRequest, VideoRequest
from .registry import (
    generate_image,
    generate_video,
    get_image_provider,
    get_video_provider,
    register_image_provider,
    register_video_provider,
)
from .fake import FakeImageProvider
from .local import LocalProceduralImageProvider
from .kaggle_voice import KaggleVoice
from .kokoro_voice import KokoroVoice
from . import bootstrap  # noqa: F401

__all__ = [
    "KaggleVoice",
    "KokoroVoice",
    "AssetResult",
    "ImageRequest",
    "VideoRequest",
    "generate_image",
    "generate_video",
    "get_image_provider",
    "get_video_provider",
    "register_image_provider",
    "register_video_provider",
    "FakeImageProvider",
    "LocalProceduralImageProvider",
]
