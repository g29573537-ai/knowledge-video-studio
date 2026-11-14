from pathlib import Path

from knowledge_video.media_rights import AssetProvenance, MediaRightsRegistry, license_is_commercially_usable


def test_allowlisted_licenses_pass_and_nc_nd_fail():
    reg = MediaRightsRegistry()
    for lic in ["CC0", "CC-BY", "CC-BY-SA", "public domain"]:
        reg.register_stock(asset_id=lic, license_short_name=lic, license_uri="https://example.com/license")
    assert reg.export_allowed() is True

    bad = MediaRightsRegistry()
    for lic in ["CC-BY-NC", "CC-BY-ND", "unknown"]:
        bad.register_stock(asset_id=lic, license_short_name=lic, license_uri="https://example.com/license" if lic != "unknown" else "")
    assert bad.export_allowed() is False
    assert bad.verify_all()


def test_missing_license_url_requires_manual_review():
    reg = MediaRightsRegistry()
    reg.register_stock(asset_id="x", license_short_name="CC-BY", license_uri="")
    assert reg.export_allowed() is False
    reg.approve_manual("x", True)
    assert reg.export_allowed() is True


def test_sha256_consistency():
    p = Path("/tmp/opencode/mr.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("data")
    from narration_video.core import file_hash

    h = file_hash(p)
    reg = MediaRightsRegistry()
    reg.register_stock(asset_id="x", license_short_name="CC0", license_uri="https://x", local_path=str(p), sha256=h, size_bytes=p.stat().st_size)
    assert reg.check_asset("x")[0] is True
    p.write_text("changed")
    assert reg.check_asset("x")[0] is False


def test_generated_media_not_commercial_by_default():
    reg = MediaRightsRegistry()
    reg.register_generated(asset_id="g", generation_provider="local", model_id="proc", prompt="hello")
    assert reg.export_allowed() is False
    assert license_is_commercially_usable("") is False
