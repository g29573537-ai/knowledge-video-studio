from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from .protocol import AssetResult, ImageRequest, VideoRequest


class FakeImageProvider:
    name = "fake"
    requires_network = False

    def generate_image(self, request: ImageRequest) -> AssetResult:
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        color = (100, 140, 180)
        Image.new("RGB", (request.width, request.height), color).save(output)
        return AssetResult(
            path=str(output),
            provider=self.name,
            model="fake",
            mime_type="image/png",
            width=request.width,
            height=request.height,
            seed=request.seed,
            metadata={
                "prompt_sha256": hashlib.sha256(request.prompt.encode()).hexdigest()
            },
        )


class FakeVideoProvider:
    name = "fake"
    requires_network = False

    def generate_video(self, request: VideoRequest) -> AssetResult:
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-video")
        return AssetResult(
            path=str(output),
            provider=self.name,
            model="fake",
            mime_type="video/mp4",
            width=request.width,
            height=request.height,
            duration=request.duration,
            seed=request.seed,
        )
