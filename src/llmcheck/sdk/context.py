from __future__ import annotations

import sys
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..storage.sqlite import mark_run_flagged


@dataclass
class LastRunRef:
    run_id: str
    storage_path: Path


_pending_context: ContextVar[list[dict[str, Any]]] = ContextVar("llmcheck_pending_context", default=[])
_pending_tags: ContextVar[dict[str, Any]] = ContextVar("llmcheck_pending_tags", default={})
_last_run: ContextVar[LastRunRef | None] = ContextVar("llmcheck_last_run", default=None)


def _normalize_context_docs(docs: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in docs:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append({"id": f"context-{len(normalized) + 1}", "text": text})
            continue
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            normalized.append(
                {
                    "id": str(item.get("id") or f"context-{len(normalized) + 1}"),
                    "text": text,
                }
            )
    return normalized


def add_context(docs: list[Any]) -> None:
    current = list(_pending_context.get())
    current.extend(_normalize_context_docs(docs))
    _pending_context.set(current)


def add_tags(tags: dict[str, Any]) -> None:
    current = dict(_pending_tags.get())
    current.update(tags)
    _pending_tags.set(current)


def flag(reason: str) -> None:
    last_run = _last_run.get()
    if last_run is None:
        print("llmcheck warning: no captured run available to flag in this context", file=sys.stderr)
        return
    updated = mark_run_flagged(last_run.storage_path, last_run.run_id, reason)
    if not updated:
        print(f"llmcheck warning: captured run `{last_run.run_id}` could not be flagged", file=sys.stderr)


def consume_pending_context() -> list[dict[str, Any]]:
    current = list(_pending_context.get())
    _pending_context.set([])
    return current


def consume_pending_tags() -> dict[str, Any]:
    current = dict(_pending_tags.get())
    _pending_tags.set({})
    return current


def set_last_run(run_id: str, storage_path: Path) -> None:
    _last_run.set(LastRunRef(run_id=run_id, storage_path=storage_path))


def clear_last_run() -> None:
    """Prevent a failed or uncaptured attempt from flagging an older response."""
    _last_run.set(None)
