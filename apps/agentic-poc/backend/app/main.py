from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from .memory import SessionMemoryStore
from .orchestrator import Orchestrator


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ClearSessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


app = FastAPI(title="Agentic Workflow POC", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
memory = SessionMemoryStore(file_path=Path(".llmcheck/agentic-poc-sessions.json"))
orchestrator = Orchestrator(memory=memory)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    result = orchestrator.run(session_id=payload.session_id, user_message=payload.message)
    return {"session_id": payload.session_id, "response": result.response, "trace": orchestrator.serialize_trace(result)}


@app.get("/sessions/{session_id}/history")
def session_history(session_id: str) -> dict[str, Any]:
    history = [asdict(msg) for msg in memory.list_messages(session_id)]
    return {"session_id": session_id, "history": history}


@app.post("/sessions/clear")
def clear_session(payload: ClearSessionRequest) -> dict[str, Any]:
    memory.clear(payload.session_id)
    return {"session_id": payload.session_id, "cleared": True}
