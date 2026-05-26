from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage.models import KnowledgeEntryRecord
from .storage.sqlite import find_applicable_knowledge_entries


@dataclass
class AppliedKnowledge:
    mode: str
    entries: list[KnowledgeEntryRecord]


def resolve_workflow(tags: dict[str, Any]) -> str | None:
    for key in ("workflow", "app", "pipeline"):
        value = tags.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def apply_retrieval_policy(
    storage_path: Path,
    *,
    messages: list[dict[str, Any]],
    tags: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[AppliedKnowledge]]:
    if not messages:
        return messages, []
    workflow = resolve_workflow(tags)
    user_text = ""
    for message in reversed(messages):
        if str(message.get("role", "")).lower() == "user":
            user_text = str(message.get("content") or "")
            break
    if not user_text.strip():
        return messages, []

    planning_entries = find_applicable_knowledge_entries(
        storage_path,
        workflow=workflow,
        query_text=user_text,
        usage_mode="retrieval_planning_only",
    )
    runtime_entries = find_applicable_knowledge_entries(
        storage_path,
        workflow=workflow,
        query_text=user_text,
        usage_mode="runtime_retrieval_allowed",
    )

    injected: list[dict[str, Any]] = []
    applied: list[AppliedKnowledge] = []

    if planning_entries:
        planning_text = "\n".join(f"- {item.title}: {item.body}" for item in planning_entries)
        injected.append(
            {
                "role": "system",
                "content": "Reviewed retrieval-planning guidance for this workflow:\n" + planning_text,
            }
        )
        applied.append(AppliedKnowledge(mode="retrieval_planning_only", entries=planning_entries))

    if runtime_entries:
        runtime_text = "\n".join(f"- {item.title}: {item.body}" for item in runtime_entries)
        injected.append(
            {
                "role": "system",
                "content": "Approved runtime context for this workflow:\n" + runtime_text,
            }
        )
        applied.append(AppliedKnowledge(mode="runtime_retrieval_allowed", entries=runtime_entries))

    return [*injected, *messages], applied
