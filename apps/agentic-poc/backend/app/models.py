from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceEvent:
    phase: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    response: str
    trace: list[TraceEvent]
