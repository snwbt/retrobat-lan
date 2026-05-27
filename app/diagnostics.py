from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig


SECRET_PATTERNS = [
    re.compile(r'(api_token\s*=\s*")[^"]+(")', re.IGNORECASE),
    re.compile(r"(X-Arcade-Token\s*[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"([?&](?:token|code)=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(arcadeToken['\"]?\s*[:,=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1[REDACTED]\2", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if "token" in str(key).lower() or "code" in str(key).lower():
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_value(item)
        return result
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def log_path(config: AppConfig) -> Path:
    return config.log_dir / "retrobat-cab-commander.log"


def tail_log(config: AppConfig, max_lines: int = 200) -> list[str]:
    path = log_path(config)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [redact_text(line) for line in lines[-max_lines:]]


def diagnostics_bundle(data: dict[str, Any]) -> str:
    return json.dumps(redact_value(data), indent=2, default=str)

