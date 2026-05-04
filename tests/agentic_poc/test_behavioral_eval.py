from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "apps" / "agentic-poc" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.memory import SessionMemoryStore
from app.orchestrator import Orchestrator


class BehavioralEvalTests(unittest.TestCase):
    def test_tool_selection_threshold(self) -> None:
        orchestrator = Orchestrator(memory=SessionMemoryStore())
        prompts = [
            "refund policy please",
            "calculate 12/3",
            "mark task done",
            "refund approval details",
            "calculate 7*8",
        ]
        expected_tools = ["knowledge_lookup", "calculator", "task_state_update", "knowledge_lookup", "calculator"]

        correct = 0
        for prompt, expected in zip(prompts, expected_tools):
            result = orchestrator.run(session_id="eval-s1", user_message=prompt)
            tool_events = [event for event in result.trace if event.phase == "execute_tool"]
            if tool_events and tool_events[0].payload.get("name") == expected:
                correct += 1

        accuracy = correct / len(prompts)
        self.assertGreaterEqual(accuracy, 0.8)

    def test_repeat_run_stability(self) -> None:
        orchestrator = Orchestrator(memory=SessionMemoryStore())
        outputs = []
        for _ in range(3):
            result = orchestrator.run(session_id="eval-s2", user_message="refund policy")
            outputs.append(result.response)
        # deterministic adapter should return stable responses for same prompt
        self.assertEqual(len(set(outputs)), 1)

    def test_runtime_error_rate(self) -> None:
        orchestrator = Orchestrator(memory=SessionMemoryStore())
        prompts = ["calculate 3+5", "refund details", "mark task done", "hello there"]
        errors = 0
        for prompt in prompts:
            try:
                orchestrator.run(session_id="eval-s3", user_message=prompt)
            except Exception:  # noqa: BLE001
                errors += 1
        error_rate = errors / len(prompts)
        self.assertLessEqual(error_rate, 0.05)


if __name__ == "__main__":
    unittest.main()
