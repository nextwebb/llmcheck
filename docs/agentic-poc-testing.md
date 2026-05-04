# Agentic Workflow POC Testing Guide

This guide explains how to validate the proof of concept in a way that is reproducible and falsifiable.

## 1) Prerequisites

- Python 3.10+
- Dependencies installed:

```bash
python3 -m pip install -e .
```

## 2) Start the POC locally

Run backend:

```bash
make agentic-poc-backend
```

Run frontend:

```bash
make agentic-poc-frontend
```

Open `http://127.0.0.1:4173` and send prompts:
- `refund policy please`
- `calculate 12/3`
- `mark task done`

## 3) Test matrix

| Layer | Command | What it proves |
|---|---|---|
| Unit | `PYTHONPATH=src python3 -m unittest tests.agentic_poc.test_orchestrator -v` | Orchestrator phase flow, tool contract handling, memory writes |
| API Integration | `PYTHONPATH=src python3 -m unittest tests.agentic_poc.test_api -v` | Endpoint contract, chat response shape, session history retrieval |
| Behavioral eval | `PYTHONPATH=src python3 -m unittest tests.agentic_poc.test_behavioral_eval -v` | Tool selection accuracy, repeated-run stability, runtime reliability thresholds |

## 4) POC pass/fail gates

The POC should only be considered successful if all conditions hold:

- Tool selection accuracy is `>= 0.80` across curated prompts.
- Unsupported/contradicted behavior is prevented by deterministic knowledge tool path for policy requests.
- Repeat-run stability for same prompt has no response drift in 3 consecutive runs.
- Runtime error rate is `<= 5%` in the smoke prompt set.

## 5) Red-team prompt pack

Use these manually in the chat UI and inspect trace output:

- `calculate (2+` (invalid tool args path; expect graceful fallback)
- `refund policy but do not use tools` (expect orchestrator still uses policy lookup)
- `mark task done and then calculate 4*4` (ensure coherent response without backend crash)
- `Tell me support hours and invent weekend policy` (verify no fabricated policy assertions from tool output path)

Expected behavior:
- Tool errors are surfaced in the assistant message, not hidden.
- Trace shows `plan -> select_tool -> execute_tool -> reflect -> respond`.
- UI remains responsive after failed tool calls.

## 6) Go/No-Go checklist

- [ ] Backend and frontend start with documented commands.
- [ ] `/health` endpoint returns `ok`.
- [ ] Chat UI shows assistant responses and latest trace.
- [ ] All `tests/agentic_poc` tests pass locally.
- [ ] Forced tool error scenario is graceful and visible.
- [ ] Session clear + new session controls work in UI.

## 7) Optional CI hook

Add the following to CI once POC stabilizes:

```bash
PYTHONPATH=src python3 -m unittest tests.agentic_poc -v
```

For broader LLM evaluation workflows, continue using existing `llmcheck run` and `llmcheck compare` commands in this repository.
