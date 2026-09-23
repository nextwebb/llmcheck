# Refund-policy regression example

Run capture, review and replay against your current LLMCheck checkout without an API key. The application returns scripted answers and the injected judge checks literal phrases. This demonstrates how files and verdicts flow through LLMCheck; it does not test a live model or measure semantic accuracy.

## Run it

From the repository root, using Python 3.10 or later:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
DEMO_OUTPUT="$(mktemp -d)"
python examples/refund-policy/offline_demo.py --output "$DEMO_OUTPUT"
python examples/refund-policy/inspect_results.py "$DEMO_OUTPUT/replay-results.json"
```

Expected verdicts:

- **FAIL**: the response promises an instant refund.
- **PASS**: the response states manager approval and 3-5 business days.
- **FAIL**: the response omits the processing time.
- **FAIL**: the response includes the policy but also promises an instant refund.

The output directory contains the captured SQLite record, its JSON export, the generated YAML draft, the explicitly reviewed YAML case, a runnable suite, replay results and source provenance. Existing nonempty output directories are rejected. The demo blocks the Python TCP connection entry points it uses and records zero live model calls. This guard is not an operating-system sandbox.

`inspect_results.py` reads saved results; it does not rerun the application or judge. To verify the full workflow and overwrite protection:

```sh
python examples/refund-policy/smoke_test.py --repo .
```

## Connect your application

The demo creates a temporary `fixture_app.answer_user` callable and injects a literal judge. Replace the callable with your application's synchronous adapter, review each case's criteria, and use the configured judge when you are ready for live evaluation. See [capture, review and replay](../../README.md#capture-review-replay) and the [RAG support example](../rag_support_agent.py).

Literal matching deliberately has limits: "not instant" contains the same word as "instant refund". The [browser explorer](https://llmcheck-demo.onrender.com/#explorer) includes negation cases and a separate, labelled recorded OpenAI evaluation. Neither mode establishes general model accuracy.
