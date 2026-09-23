from __future__ import annotations

import time
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..retrieval_policy import apply_retrieval_policy
from ..storage.models import RunRecord
from ..storage.sqlite import init_db, save_run
from .context import clear_last_run, consume_pending_context, consume_pending_tags, set_last_run


def _default_storage_path() -> Path:
    return Path(".llmcheck/llmcheck.db").resolve()


def _extract_output_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(getattr(item, "text", "")))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return dict(usage.model_dump())
    if hasattr(usage, "__dict__"):
        return dict(vars(usage))
    return {}


def _extract_user_input(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        if str(message.get("role", "")).lower() == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None


def instrument_openai(client: Any, *, storage_path: str | Path | None = None) -> Any:
    if client is None:
        raise ValueError("instrument_openai requires an OpenAI client instance")

    target_path = Path(storage_path).resolve() if storage_path else _default_storage_path()
    init_db(target_path)

    create = client.chat.completions.create

    def wrapped_create(*args: Any, **kwargs: Any) -> Any:
        # Context and tags belong to one attempted call, including failed calls.
        clear_last_run()
        context = consume_pending_context()
        tags = consume_pending_tags()
        messages = kwargs.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        messages, applied_knowledge = apply_retrieval_policy(
            target_path,
            messages=messages,
            tags=tags,
        )
        kwargs = dict(kwargs)
        kwargs["messages"] = messages

        start = time.perf_counter()
        try:
            response = create(*args, **kwargs)
        except BaseException:
            clear_last_run()
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            record = RunRecord(
                id=f"run_{uuid.uuid4().hex[:12]}",
                created_at=datetime.now(timezone.utc).isoformat(),
                name=kwargs.get("model"),
                input_json={
                    "model": kwargs.get("model"),
                    "messages": messages,
                    "user_input": _extract_user_input(messages),
                },
                output_text=_extract_output_text(response),
                messages=messages,
                context=context,
                tags=tags,
                metadata={
                    "model": kwargs.get("model"),
                    "latency_ms": latency_ms,
                    "usage": _extract_usage(response),
                    "applied_knowledge": [
                        {
                            "mode": item.mode,
                            "entry_ids": [entry.id for entry in item.entries],
                            "titles": [entry.title for entry in item.entries],
                        }
                        for item in applied_knowledge
                    ],
                },
            )
            save_run(target_path, record)
            set_last_run(record.id, target_path)
        except Exception:
            clear_last_run()
            # Do not expose captured content or exception text, or turn a
            # successful provider call into an apparent provider failure.
            print("llmcheck warning: response received but local capture failed; this response cannot be flagged", file=sys.stderr)
        return response

    client.chat.completions.create = wrapped_create
    return client
