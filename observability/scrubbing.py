"""Shared scrubbing helpers for future OpenLIT/Sentry integrations.

This module is importable but does not initialize or send any telemetry.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SECRET_KEY_NAMES = {
    "api_key",
    "authorization",
    "token",
    "secret",
    "password",
    "hf_token",
    "kaggle_key",
    "kilocode_api_key",
}


def scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_KEY_NAMES:
                result[key] = "<redacted>"
            else:
                result[key] = scrub_value(item)
        return result
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, str):
        # Redact common token-like strings and home/workspace paths.
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1<redacted>", value)
        value = re.sub(r"/(?:home|workspaces|tmp)/[^\s'\"]+", "<path>", value)
        for env_name in ("KILOCODE_API_KEY", "HF_TOKEN", "KAGGLE_KEY", "GITHUB_TOKEN"):
            env_value = os.environ.get(env_name)
            if env_value and env_value in value:
                value = value.replace(env_value, "<redacted>")
        return value
    return value


def safe_path(path: str | Path) -> str:
    return (
        str(path)
        .replace(str(Path.home()), "<home>")
        .replace("/workspaces", "<workspaces>")
    )
