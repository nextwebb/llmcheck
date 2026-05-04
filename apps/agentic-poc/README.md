# Agentic Workflow POC

This app demonstrates a local-first single-agent workflow with:
- a FastAPI chat backend,
- deterministic tool-calling orchestration,
- a lightweight browser chat interface with trace inspection.

## Run locally

Terminal 1:

```bash
make agentic-poc-backend
```

Terminal 2:

```bash
make agentic-poc-frontend
```

Open: `http://127.0.0.1:4173`.
