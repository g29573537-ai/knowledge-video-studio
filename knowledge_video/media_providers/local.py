from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from .protocol import AssetResult, ImageRequest


class LocalProceduralImageProvider:
    name = "local"
    requires_network = False

    def generate_image(self, request: ImageRequest) -> AssetResult:
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (request.width, request.height), "#1f2937")
        draw = ImageDraw.Draw(image)
        if request.width > 40 and request.height > 40:
            draw.rectangle(
                (20, 20, request.width - 20, request.height - 20),
                outline="#93c5fd",
                width=4,
            )
        draw.text((40, 40), request.prompt[:80], fill="white")
        image.save(output)
        return AssetResult(
            path=str(output),
            provider=self.name,
            model="procedural",
            mime_type="image/png",
            width=request.width,
            height=request.height,
            seed=request.seed,
            metadata={
                "prompt_sha256": hashlib.sha256(request.prompt.encode()).hexdigest()
            },
        )
