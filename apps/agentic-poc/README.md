# Experimental agent workflow

A separate local prototype with a FastAPI backend, deterministic tool selection and a browser interface for inspecting traces. It is not part of the hosted refund-policy explorer or a validated production agent.

## Run from a source checkout

Use Python 3.10 or later and an activated virtual environment. From the repository root:

```sh
python -m pip install fastapi uvicorn
python -m uvicorn app.main:app --app-dir apps/agentic-poc/backend --host 127.0.0.1 --port 8000
```

In another terminal at the repository root:

```sh
python -m http.server 4173 --bind 127.0.0.1 --directory apps/agentic-poc/frontend
```

Open `http://127.0.0.1:4173`. The backend stores local session history under `.llmcheck/`. There is no committed automated test suite for this app; inspect health, responses, traces and session clearing manually. See the [testing note](../../docs/agentic-poc-testing.md).
