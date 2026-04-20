from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CaseSpec


class TraceError(Exception):
    pass


def _normalize_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    tool = event.get("tool") or event.get("tool_name") or event.get("name")
    if not isinstance(tool, str) or not tool.strip():
        raise TraceError(f"trace event {index} missing tool/tool_name/name")

    args = event.get("arguments")
    if args is None:
        args = event.get("args")
    if args is None:
        args = event.get("input")
    if args is None:
        args = {}

    if not isinstance(args, dict):
        raise TraceError(f"trace event {index} arguments/args/input must be an object")

    return {
        "index": index,
        "tool": tool,
        "timestamp": event.get("timestamp"),
        "step_id": event.get("step_id") or event.get("span_id"),
        "arguments": args,
        "result": event.get("result"),
        "raw": event,
    }


def _load_trace_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise TraceError(f"trace file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TraceError(f"trace file is not valid JSON: {path}") from exc

    if isinstance(raw, dict):
        events = raw.get("events")
    else:
        events = raw

    if not isinstance(events, list):
        raise TraceError(f"trace file must contain a list of events: {path}")

    normalized: list[dict[str, Any]] = []
    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            raise TraceError(f"trace event {idx} must be an object")
        normalized.append(_normalize_event(event, idx))
    return normalized


def load_case_trace_events(case: CaseSpec) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, event in enumerate(case.trace_events):
        events.append(_normalize_event(event, idx))

    if case.trace_file is not None:
        file_events = _load_trace_file(case.trace_file)
        start = len(events)
        for offset, event in enumerate(file_events):
            event["index"] = start + offset
            events.append(event)

    return events
