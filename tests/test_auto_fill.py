from pathlib import Path

from knowledge_video.media_rights import MediaRightsRegistry
from knowledge_video.visuals import auto_fill_secondary_visuals


def make_beat(role, bid="b1"):
    return {
        "id": bid,
        "visual_role": role,
        "visual_object": "diagram",
        "phrase": "phrase",
        "media_source": {"type": "unknown", "asset_ref": None},
    }


def test_secondary_generates_and_hero_does_not(tmp_path):
    beats = [make_beat("hero", "hero1"), make_beat("secondary", "sec1")]
    registry = MediaRightsRegistry()
    results = auto_fill_secondary_visuals(beats, registry=registry, output_dir=tmp_path)
    assert results[0] is None
    assert results[1] is not None
    assert Path(results[1].output_path).exists()
    assert beats[1]["asset_ref"] is not None
    # Generated asset is not commercial by default.
    assert registry.export_allowed() is False


def test_rerun_reuses_valid_file_and_hash(tmp_path):
    beats = [make_beat("secondary", "sec2")]
    registry = MediaRightsRegistry()
    first = auto_fill_secondary_visuals(beats, registry=registry, output_dir=tmp_path)[0]
    from narration_video.core import file_hash

    h1 = file_hash(Path(first.output_path))
    second = auto_fill_secondary_visuals(beats, registry=registry, output_dir=tmp_path)[0]
    h2 = file_hash(Path(second.output_path))
    assert h1 == h2
    assert second.cache_key == first.cache_key


def test_failed_qc_is_not_masked(tmp_path):
    from knowledge_video.visuals import generate_scene_visual

    original = generate_scene_visual

    def failing(*args, **kwargs):
        # Simulate AI failure with fallback.
        kwargs["generate_diffusion"] = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad"))
        kwargs["visual_mode"] = "local_diffusion"
        kwargs["ai_fallback_enabled"] = True
        kwargs["scene_role"] = "secondary"
        kwargs["diffusion_available"] = lambda: True
        kwargs["diffusion_model_present"] = lambda: True
        return original(*args, **kwargs)

    # Patch generate_scene_visual used by auto_fill
    import knowledge_video.visuals as v

    v.generate_scene_visual = failing
    try:
        beats = [make_beat("secondary", "sec3")]
        registry = MediaRightsRegistry()
        res = auto_fill_secondary_visuals(beats, registry=registry, output_dir=tmp_path)[0]
        assert res.fallback_used is True
        assert registry.export_allowed() is False
    finally:
        v.generate_scene_visual = original
