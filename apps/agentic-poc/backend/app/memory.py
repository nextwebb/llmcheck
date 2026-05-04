from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import ChatMessage


class SessionMemoryStore:
    def __init__(self, file_path: Path | None = None) -> None:
        self._sessions: dict[str, list[ChatMessage]] = {}
        self._file_path = file_path
        if self._file_path and self._file_path.exists():
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
            for session_id, items in payload.items():
                self._sessions[session_id] = [ChatMessage(**item) for item in items]

    def append(self, session_id: str, message: ChatMessage) -> None:
        self._sessions.setdefault(session_id, []).append(message)
        self._persist()

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        return list(self._sessions.get(session_id, []))

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._persist()

    def _persist(self) -> None:
        if not self._file_path:
            return
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        dump = {session_id: [asdict(msg) for msg in msgs] for session_id, msgs in self._sessions.items()}
        self._file_path.write_text(json.dumps(dump, indent=2), encoding="utf-8")
