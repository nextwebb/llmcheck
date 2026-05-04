from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAIResponse:
    text: str
    tool_call: dict[str, Any] | None = None


class OpenAIAdapter:
    """Local POC adapter.

    This is intentionally deterministic for repeatable tests unless
    `OPENAI_API_KEY` integration is added later.
    """

    def chat(self, *, user_message: str, memory_summary: str) -> OpenAIResponse:
        text = user_message.lower()
        if "refund" in text:
            return OpenAIResponse(
                text="I will check the policy first.",
                tool_call={"name": "knowledge_lookup", "arguments": {"topic": "refund_policy"}},
            )
        if "calculate" in text:
            expression = user_message.split("calculate", 1)[-1].strip() or "0"
            return OpenAIResponse(
                text="I will calculate that.",
                tool_call={"name": "calculator", "arguments": {"expression": expression}},
            )
        if "mark task" in text:
            return OpenAIResponse(
                text="I will update task status.",
                tool_call={"name": "task_state_update", "arguments": {"task_id": "poc-task", "state": "done"}},
            )
        return OpenAIResponse(
            text=f"Based on your message and recent context ({memory_summary}), here is a concise answer: {user_message}"
        )
