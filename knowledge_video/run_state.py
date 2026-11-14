"""Crash-safe run state for Knowledge Video Studio.

This strengthens the existing KVS job lifecycle instead of adding a second queue.
The durable state is written atomically (temp file -> replace) and records input
fingerprints, per-stage manifests, heartbeats/TTLs and artifact integrity.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .runtime import atomic_json


def fingerprint_inputs(inputs: Any) -> str:
    """Canonical SHA-256 fingerprint, following the AIF run_store.py idea."""

    def default(value):
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "model_dump"):
            return value.model_dump()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    canonical = json.dumps(
        inputs,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunStore:
    """Small durable manifest store.  It is intentionally dependency-free."""

    def __init__(self, root, filename: str = "run_state.json", ttl_seconds: int = 300):
        self.root = Path(root)
        self.path = self.root / filename
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def fingerprint_inputs(inputs: Any) -> str:
        return fingerprint_inputs(inputs)

    def _read(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        atomic_json(self.path, manifest)

    def start(
        self,
        inputs: Any = None,
        run_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        manifest = {
            "run_id": run_id or uuid.uuid4().hex,
            "status": "running",
            "input_fingerprint": fingerprint_inputs(inputs if inputs is not None else {}),
            "created_at": time.time(),
            "started_at": time.time(),
            "heartbeat_at": time.time(),
            "ttl_seconds": ttl,
            "current_stage": None,
            "stages": {},
            "artifacts": {},
            "events": [],
        }
        self._write_manifest(manifest)
        return manifest

    def resume(self) -> dict[str, Any] | None:
        manifest = self._read()
        if manifest is None:
            return None
        ttl = float(manifest.get("ttl_seconds", self.ttl_seconds))
        heartbeat = float(manifest.get("heartbeat_at", manifest.get("started_at", 0.0)))
        if manifest.get("status") == "running" and time.time() - heartbeat > ttl:
            manifest["status"] = "interrupted"
            manifest["message"] = "heartbeat TTL expired"
            self._write_manifest(manifest)
        return manifest

    def heartbeat(self, stage: str | None = None) -> dict[str, Any]:
        manifest = self._read()
        if manifest is None:
            manifest = self.start({})
        manifest["heartbeat_at"] = time.time()
        if stage is not None:
            manifest["current_stage"] = stage
        self._write_manifest(manifest)
        return manifest

    def _record_artifact_integrity(self, path: Any) -> dict[str, Any]:
        from narration_video.core import file_hash

        p = Path(path)
        if not p.exists():
            return {"path": str(p), "exists": False, "sha256": None, "size_bytes": 0}
        return {
            "path": str(p),
            "exists": True,
            "sha256": file_hash(p),
            "size_bytes": p.stat().st_size,
        }

    def record_artifact(self, key: str, path: Any) -> dict[str, Any]:
        manifest = self._read()
        if manifest is None:
            manifest = self.start({})
        info = self._record_artifact_integrity(path)
        manifest.setdefault("artifacts", {})[key] = info
        self._write_manifest(manifest)
        return info

    def record_stage(
        self,
        stage: str,
        status: str = "completed",
        artifacts: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        manifest = self._read()
        if manifest is None:
            manifest = self.start({})
        artifact_info = {}
        for key, path in (artifacts or {}).items():
            artifact_info[key] = self._record_artifact_integrity(path)
        manifest.setdefault("stages", {})[stage] = {
            "status": status,
            "completed_at": time.time(),
            "artifacts": artifact_info,
            "metadata": metadata or {},
        }
        manifest["current_stage"] = stage
        manifest["heartbeat_at"] = time.time()
        self._write_manifest(manifest)
        return manifest

    def stage_completed(self, stage: str) -> bool:
        manifest = self._read()
        if not manifest:
            return False
        stage_state = manifest.get("stages", {}).get(stage, {})
        if stage_state.get("status") != "completed":
            return False
        for info in stage_state.get("artifacts", {}).values():
            if not info.get("exists"):
                return False
            path = Path(info["path"])
            if not path.exists():
                return False
            if info.get("sha256") is not None:
                from narration_video.core import file_hash

                if file_hash(path) != info["sha256"]:
                    return False
            if info.get("size_bytes") is not None and path.stat().st_size != info["size_bytes"]:
                return False
        return True

    def complete(self) -> dict[str, Any]:
        manifest = self._read()
        if manifest is None:
            manifest = self.start({})
        manifest["status"] = "completed"
        manifest["completed_at"] = time.time()
        manifest["heartbeat_at"] = time.time()
        self._write_manifest(manifest)
        return manifest

    def invalidate_downstream(self, stage: str) -> dict[str, Any] | None:
        manifest = self._read()
        if not manifest:
            return None
        stages = manifest.get("stages", {})
        order = list(stages.keys())
        if stage not in order:
            return manifest
        index = order.index(stage)
        for name in order[index + 1 :]:
            stages.pop(name, None)
        if stage in stages and stages[stage].get("status") == "completed":
            stages[stage]["status"] = "invalidated"
        self._write_manifest(manifest)
        return manifest

    # Compatibility names.
    def _record_artifact(self, path: Any) -> dict[str, Any]:
        return self._record_artifact_integrity(path)
