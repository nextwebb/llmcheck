from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "apps" / "agentic-poc" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.memory import SessionMemoryStore
from app.orchestrator import Orchestrator


class OrchestratorTests(unittest.TestCase):
    def test_refund_query_uses_knowledge_tool(self) -> None:
        orchestrator = Orchestrator(memory=SessionMemoryStore())
        result = orchestrator.run(session_id="s1", user_message="Can you summarize the refund policy?")
        self.assertIn("Tool result", result.response)
        phases = [event.phase for event in result.trace]
        self.assertEqual(phases, ["plan", "select_tool", "execute_tool", "reflect", "respond"])

    def test_tool_failure_graceful_fallback(self) -> None:
        orchestrator = Orchestrator(memory=SessionMemoryStore())
        result = orchestrator.run(session_id="s1", user_message="calculate (2+")
        self.assertIn("tool issue", result.response.lower())

    def test_memory_is_written(self) -> None:
        memory = SessionMemoryStore()
        orchestrator = Orchestrator(memory=memory)
        orchestrator.run(session_id="s2", user_message="hello")
        history = memory.list_messages("s2")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[1].role, "assistant")


if __name__ == "__main__":
    unittest.main()
