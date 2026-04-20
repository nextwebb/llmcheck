from __future__ import annotations

import json
import re
from typing import Any


_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]{12,})"),
    re.compile(r"(AIza[0-9A-Za-z_-]{20,})"),
]


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def maybe_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def json_path_get(obj: Any, path: str) -> Any:
    if not path:
        return obj

    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
            continue

        if isinstance(current, list):
            try:
                idx = int(part)
            except ValueError as exc:
                raise KeyError(path) from exc
            try:
                current = current[idx]
            except IndexError as exc:
                raise KeyError(path) from exc
            continue

        raise KeyError(path)

    return current


def normalize_output(text: str, structured: Any) -> dict[str, Any]:
    normalized_text = "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()
    return {
        "text": normalized_text,
        "structured": structured,
    }
