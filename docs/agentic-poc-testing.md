# Experimental agent workflow

The app in `apps/agentic-poc` is a separate local experiment. It is not the hosted refund-policy explorer or the core capture/review/replay workflow. Its previously documented Make targets and `tests/agentic_poc` suite are not present in this checkout; no automated app-quality gate is claimed.

See the [app README](../apps/agentic-poc/README.md) for direct launch commands. Manually inspect `/health`, a refund-policy reply, its trace and session clearing when changing the app. A successful smoke check is not a behavioral benchmark.

The supported core tests run with:

```sh
python -m pip install -e '.[test]'
python -m pytest -q
```

For reviewed regression cases, use `llmcheck run-suite -c llmcheck.yaml --suite llmcheck_suite.yaml`. See the [CLI reference](reference.md) for configuration and supported commands.
