from pathlib import Path

from knowledge_video.visuals import generate_scene_visual


def test_without_flag_ai_not_called(tmp_path):
    calls = {"n": 0}

    def diffusion_available():
        calls["n"] += 1
        return True

    def model_present():
        return True

    out = tmp_path / "a.png"
    res = generate_scene_visual(
        "hello",
        output=out,
        visual_mode="procedural",
        diffusion_available=diffusion_available,
        diffusion_model_present=model_present,
    )
    assert res.backend == "procedural"
    assert calls["n"] == 0


def test_ai_error_falls_back_only_when_allowed(tmp_path):
    out = tmp_path / "b.png"

    def boom(*args, **kwargs):
        raise RuntimeError("ai down")

    res = generate_scene_visual(
        "hello",
        output=out,
        visual_mode="local_diffusion",
        ai_fallback_enabled=True,
        scene_role="secondary",
        diffusion_available=lambda: True,
        diffusion_model_present=lambda: True,
        generate_diffusion=boom,
    )
    assert res.fallback_used is True
    assert res.backend == "procedural"
    assert out.exists()

    out2 = tmp_path / "c.png"
    try:
        generate_scene_visual(
            "hello",
            output=out2,
            visual_mode="local_diffusion",
            ai_fallback_enabled=False,
            scene_role="hero",
            diffusion_available=lambda: True,
            diffusion_model_present=lambda: True,
            generate_diffusion=boom,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("fallback should not happen for disallowed scene")
