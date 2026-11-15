"""Media rights and provenance registry for Knowledge Video Studio.

Provenance allowlist/attribution ideas are reimplemented from
summitsingh/ai-video-factory ``src/ai_video_factory/stock_media.py`` (MIT).
AI-generated media has a separate provenance record and is never assumed to be
commercially usable by default.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .runtime import atomic_json

VerificationStatus = Literal[
    "verified",
    "unverified",
    "manual_review",
    "manual_approved",
    "approved",
    "rejected",
]

ALLOWED_LICENSES = {
    "cc0",
    "cc0-1.0",
    "cc 0",
    "public domain",
    "pd",
    "cc-by",
    "cc-by-4.0",
    "cc-by-3.0",
    "cc-by-2.0",
    "cc-by-sa",
    "cc-by-sa-4.0",
    "cc-by-sa-3.0",
    "cc-by-sa-2.0",
}

REJECTED_LICENSE_TOKENS = (
    "nc",
    "nd",
    "noncommercial",
    "no-derivatives",
    "non-commercial",
)


def _normalize_license(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", "-").split())


def license_is_commercially_usable(value: str) -> bool:
    normalized = _normalize_license(value)
    if not normalized:
        return False
    if any(token in normalized for token in REJECTED_LICENSE_TOKENS):
        return False
    return normalized in ALLOWED_LICENSES


class AssetProvenance(BaseModel):
    asset_id: str
    provider: str = ""
    title: str = ""
    creator: str = ""
    license_short_name: str = ""
    license_uri: str = ""
    source_page_url: str = ""
    original_file_url: str = ""
    attribution_text: str = ""
    retrieved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    local_path: str = ""
    sha256: str = ""
    size_bytes: int = 0
    mime_type: str = ""
    commercial_use: bool = False
    attribution_required: bool = True
    usage_terms_url: str = ""
    verification_status: VerificationStatus = "unverified"
    rejection_reason: str = ""

    # Provenance for generated media.  These are intentionally separate from the
    # stock-media license fields and default to "not approved".
    generation_provider: str = ""
    model_id: str = ""
    model_version: str = ""
    weights_license_url: str = ""
    provider_terms_url: str = ""
    terms_checked_at: str = ""
    prompt_sha256: str = ""
    seed: int | None = None
    generated_at: str = ""

    def is_generated(self) -> bool:
        return bool(self.generation_provider or self.model_id)

    def verify(self) -> list[str]:
        if self.verification_status in {"manual_approved", "approved"}:
            return []
        reasons: list[str] = []
        if self.is_generated():
            if not self.generation_provider:
                reasons.append("missing generation provider")
            if not self.model_id:
                reasons.append("missing model id")
            if not self.weights_license_url and not self.provider_terms_url:
                reasons.append("missing weights/API terms")
            if not self.terms_checked_at:
                reasons.append("terms not checked")
            if not self.prompt_sha256:
                reasons.append("missing prompt hash")
            if (
                self.verification_status
                not in {"verified", "approved", "manual_approved"}
                and not reasons
            ):
                reasons.append("generated media not approved")
        else:
            normalized_license = _normalize_license(self.license_short_name)
            if not normalized_license:
                reasons.append("missing license")
            elif normalized_license not in ALLOWED_LICENSES:
                reasons.append(f"license not allowlisted: {self.license_short_name}")
            if any(token in normalized_license for token in REJECTED_LICENSE_TOKENS):
                reasons.append(f"rejected license: {self.license_short_name}")
            if not self.license_uri:
                reasons.append("missing license URL")
            if not license_is_commercially_usable(self.license_short_name):
                reasons.append("not commercially usable")
        if self.rejection_reason:
            reasons.append(self.rejection_reason)
        return reasons

    def mark_verified(self) -> None:
        self.verification_status = "verified"
        self.commercial_use = (
            license_is_commercially_usable(self.license_short_name)
            or self.is_generated()
        )
        if self.is_generated():
            # Generated media stays non-commercial until terms are explicitly checked.
            self.commercial_use = bool(
                self.weights_license_url or self.provider_terms_url
            ) and bool(self.terms_checked_at)
        self.rejection_reason = ""

    def mark_manual_review(self, approved: bool, reason: str = "") -> None:
        if approved:
            self.verification_status = "manual_approved"
            self.commercial_use = True
            self.rejection_reason = ""
        else:
            self.verification_status = "rejected"
            self.commercial_use = False
            self.rejection_reason = reason or "manual review rejected"

    def check_file(self, path: str | Path | None = None) -> list[str]:
        target = (
            Path(path) if path else Path(self.local_path) if self.local_path else None
        )
        reasons = []
        if not target or not target.exists() or target.is_dir():
            if self.local_path or path:
                reasons.append("missing local file")
            return reasons
        from narration_video.core import file_hash

        actual = file_hash(Path(target))
        if self.sha256 and actual != self.sha256:
            reasons.append("sha256 mismatch")
        if self.size_bytes and Path(target).stat().st_size != self.size_bytes:
            reasons.append("size mismatch")
        return reasons


class MediaRightsRegistry:
    def __init__(self, assets: list[AssetProvenance] | None = None):
        self.assets: list[AssetProvenance] = list(assets or [])

    def add(self, asset: AssetProvenance) -> AssetProvenance:
        self.assets.append(asset)
        return asset

    def add_asset(self, asset: AssetProvenance) -> AssetProvenance:
        return self.add(asset)

    def register(self, asset: AssetProvenance) -> AssetProvenance:
        return self.add(asset)

    def register_stock(
        self,
        *,
        asset_id: str,
        provider: str = "",
        title: str = "",
        creator: str = "",
        license_short_name: str = "",
        license_uri: str = "",
        source_page_url: str = "",
        original_file_url: str = "",
        attribution_text: str = "",
        local_path: str = "",
        sha256: str = "",
        size_bytes: int = 0,
        mime_type: str = "",
        usage_terms_url: str = "",
        retrieved_at: str | None = None,
    ) -> AssetProvenance:
        asset = AssetProvenance(
            asset_id=asset_id,
            provider=provider,
            title=title,
            creator=creator,
            license_short_name=license_short_name,
            license_uri=license_uri,
            source_page_url=source_page_url,
            original_file_url=original_file_url,
            attribution_text=attribution_text,
            retrieved_at=retrieved_at or datetime.now(UTC).isoformat(),
            local_path=local_path,
            sha256=sha256,
            size_bytes=size_bytes,
            mime_type=mime_type,
            usage_terms_url=usage_terms_url or license_uri,
            commercial_use=license_is_commercially_usable(license_short_name),
            attribution_required=True,
            verification_status="verified"
            if license_is_commercially_usable(license_short_name) and license_uri
            else "manual_review",
        )
        return self.add(asset)

    def register_generated(
        self,
        *,
        asset_id: str,
        generation_provider: str,
        model_id: str,
        model_version: str = "",
        weights_license_url: str = "",
        provider_terms_url: str = "",
        terms_checked_at: str = "",
        prompt: str = "",
        prompt_sha256: str = "",
        seed: int | None = None,
        local_path: str = "",
        sha256: str = "",
        size_bytes: int = 0,
        mime_type: str = "",
        retrieved_at: str | None = None,
    ) -> AssetProvenance:
        asset = AssetProvenance(
            asset_id=asset_id,
            provider=generation_provider,
            title=f"Generated asset {asset_id}",
            license_short_name="",
            license_uri=weights_license_url or provider_terms_url,
            source_page_url=provider_terms_url,
            original_file_url="",
            attribution_text="AI-generated media; rights depend on model/API terms.",
            retrieved_at=retrieved_at or datetime.now(UTC).isoformat(),
            local_path=local_path,
            sha256=sha256,
            size_bytes=size_bytes,
            mime_type=mime_type,
            commercial_use=False,
            attribution_required=False,
            usage_terms_url=weights_license_url or provider_terms_url,
            verification_status="unverified",
            generation_provider=generation_provider,
            model_id=model_id,
            model_version=model_version,
            weights_license_url=weights_license_url,
            provider_terms_url=provider_terms_url,
            terms_checked_at=terms_checked_at,
            prompt_sha256=prompt_sha256
            or (hashlib.sha256(prompt.encode()).hexdigest() if prompt else ""),
            seed=seed,
            generated_at=datetime.now(UTC).isoformat(),
        )
        return self.add(asset)

    def get(self, asset_id: str) -> AssetProvenance | None:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    def check_asset(self, asset: AssetProvenance | str) -> tuple[bool, list[str]]:
        target = self.get(asset) if isinstance(asset, str) else asset
        if target is None:
            return False, ["asset not found"]
        reasons = target.verify()
        reasons.extend(target.check_file())
        return len(reasons) == 0, reasons

    def check(self, asset: AssetProvenance | str) -> tuple[bool, list[str]]:
        return self.check_asset(asset)

    def verify_all(self) -> list[str]:
        reasons: list[str] = []
        for asset in self.assets:
            ok, asset_reasons = self.check_asset(asset)
            if not ok:
                reasons.extend(f"{asset.asset_id}: {r}" for r in asset_reasons)
        return reasons

    def export_allowed(self) -> bool:
        return len(self.verify_all()) == 0 and all(
            a.commercial_use
            and a.verification_status in {"verified", "approved", "manual_approved"}
            for a in self.assets
        )

    def can_export(self) -> bool:
        return self.export_allowed()

    def is_export_allowed(self) -> bool:
        return self.export_allowed()

    def approve_manual(
        self, asset_id: str, approved: bool = True, reason: str = ""
    ) -> None:
        asset = self.get(asset_id)
        if asset is None:
            raise KeyError(asset_id)
        asset.mark_manual_review(approved, reason)

    def write_sidecar(self, path: str | Path) -> None:
        atomic_json(
            Path(path),
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "assets": [a.model_dump() for a in self.assets],
                "export_allowed": self.export_allowed(),
                "issues": self.verify_all(),
            },
        )

    def write_attribution_log(self, path: str | Path) -> None:
        self.write_sidecar(path)

    def dump(self, path: str | Path) -> None:
        self.write_sidecar(path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assets": [a.model_dump() for a in self.assets],
            "export_allowed": self.export_allowed(),
            "issues": self.verify_all(),
        }

    @classmethod
    def from_sidecar(cls, path: str | Path) -> MediaRightsRegistry:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assets = [AssetProvenance.model_validate(x) for x in data.get("assets", [])]
        return cls(assets)
