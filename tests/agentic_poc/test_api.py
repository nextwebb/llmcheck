from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "apps" / "agentic-poc" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.main as main_mod
from app.memory import SessionMemoryStore
from app.orchestrator import Orchestrator


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        # Route handlers close over module globals; replace with an in-memory store so tests
        # do not leak state via `.llmcheck/agentic-poc-sessions.json` or depend on test order.
        main_mod.memory = SessionMemoryStore(file_path=None)
        main_mod.orchestrator = Orchestrator(memory=main_mod.memory)
        self.client = TestClient(main_mod.app)

    def test_health(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_chat_and_history(self) -> None:
        session_id = "api-session-1"
        chat = self.client.post("/chat", json={"session_id": session_id, "message": "refund details please"})
        self.assertEqual(chat.status_code, 200)
        body = chat.json()
        self.assertIn("response", body)
        self.assertGreaterEqual(len(body["trace"]), 4)

        history = self.client.get(f"/sessions/{session_id}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["history"]), 2)

    def test_invalid_payload(self) -> None:
        resp = self.client.post("/chat", json={"session_id": "", "message": ""})
        self.assertEqual(resp.status_code, 422)

    def test_cors_allows_dev_frontend_origin(self) -> None:
        resp = self.client.post(
            "/chat",
            json={"session_id": "cors-session", "message": "hello"},
            headers={"Origin": "http://127.0.0.1:4173"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://127.0.0.1:4173")


if __name__ == "__main__":
    unittest.main()
