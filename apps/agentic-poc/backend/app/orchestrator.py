from __future__ import annotations

from dataclasses import asdict

from .llm.openai_adapter import OpenAIAdapter
from .memory import SessionMemoryStore
from .models import AgentRunResult, ChatMessage, TraceEvent
from .tools import execute_tool


class Orchestrator:
    def __init__(self, memory: SessionMemoryStore, llm: OpenAIAdapter | None = None) -> None:
        self.memory = memory
        self.llm = llm or OpenAIAdapter()

    def run(self, *, session_id: str, user_message: str) -> AgentRunResult:
        trace: list[TraceEvent] = []
        history = self.memory.list_messages(session_id)
        summary = f"{len(history)} prior messages"

        trace.append(TraceEvent(phase="plan", payload={"session_id": session_id, "history_count": len(history)}))

        model_response = self.llm.chat(user_message=user_message, memory_summary=summary)
        trace.append(TraceEvent(phase="select_tool", payload={"tool_call": model_response.tool_call}))

        tool_result_payload = None
        if model_response.tool_call:
            tool_name = model_response.tool_call.get("name", "")
            arguments = model_response.tool_call.get("arguments", {})
            tool_result = execute_tool(tool_name, arguments)
            tool_result_payload = {"ok": tool_result.ok, "output": tool_result.output, "error": tool_result.error}
            trace.append(
                TraceEvent(
                    phase="execute_tool",
                    payload={"name": tool_name, "arguments": arguments, "result": tool_result_payload},
                )
            )

        if tool_result_payload and tool_result_payload.get("ok"):
            final = f"{model_response.text} Tool result: {tool_result_payload['output']}"
        elif tool_result_payload and not tool_result_payload.get("ok"):
            final = (
                f"{model_response.text} I hit a tool issue ({tool_result_payload['error']}) "
                "and continued with a best-effort response."
            )
        else:
            final = model_response.text

        trace.append(TraceEvent(phase="reflect", payload={"tool_used": bool(tool_result_payload)}))
        trace.append(TraceEvent(phase="respond", payload={"response_preview": final[:120]}))

        self.memory.append(session_id, ChatMessage(role="user", content=user_message))
        self.memory.append(session_id, ChatMessage(role="assistant", content=final))
        return AgentRunResult(response=final, trace=trace)

    @staticmethod
    def serialize_trace(result: AgentRunResult) -> list[dict]:
        return [asdict(event) for event in result.trace]
