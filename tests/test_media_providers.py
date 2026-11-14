import json
from pathlib import Path

from knowledge_video.media_providers import (
    ImageRequest,
    generate_image,
    get_image_provider,
    register_image_provider,
)
from knowledge_video.media_providers.fake import FakeImageProvider
from knowledge_video.media_providers.protocol import AssetResult


def test_provider_model_allowlist_and_unknown_provider(tmp_path):
    register_image_provider("fake2", FakeImageProvider(), {"fake"})
    with __import__("pytest").raises(ValueError):
        get_image_provider("nope")
    with __import__("pytest").raises(ValueError):
        get_image_provider("fake2", "not-allowed")


def test_timeout_failure_mapping_and_key_not_serialized(tmp_path):
    class BadProvider(FakeImageProvider):
        name = "bad"

        def generate_image(self, request):
            raise TimeoutError("boom")

    register_image_provider("bad", BadProvider(), {"fake"})
    try:
        generate_image(ImageRequest(prompt="x", output_path=tmp_path / "a.png"), provider="bad")
    except TimeoutError:
        pass
    else:
        raise AssertionError("expected timeout")
    # key serialization check is about request.json in jobs, but ensure provider metadata has no secret
    result = generate_image(ImageRequest(prompt="x", output_path=tmp_path / "b.png"), provider="fake")
    assert isinstance(result, AssetResult)
    assert "api_key" not in json.dumps(result.to_dict())


def test_file_path_and_format_validation(tmp_path):
    out = tmp_path / "img.png"
    result = generate_image(ImageRequest(prompt="hello", output_path=out, width=16, height=16), provider="local")
    assert Path(result.path).exists()
    assert result.width == 16 and result.height == 16
    assert result.sha256
