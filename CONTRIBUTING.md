# Contributing

Use Python 3.10 or later and an isolated environment. Do not commit `.env`, API keys, workspace databases, customer examples or generated evaluation records containing private data.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

Tests should use synthetic data and injected provider responses. Label live experiments separately, including the model, configuration, input scope and observed result. A provider mock verifies integration behavior, not semantic evaluation quality.

Before proposing a release:

```bash
python -m pip install build
python -m build
pytest -q tests/test_build_backend.py
```

Install the built wheel in a fresh environment outside the repository and run `llmcheck --help`. Build a wheel from the source distribution too. Confirm package files, console entry points and the synthetic demo are available without the original source tree. The packaging tests exercise portability and archive exclusions.

Keep `pyproject.toml` and `llmcheck.__version__` aligned. The build backend reads the distribution version from `pyproject.toml`. Update CHANGELOG.md, review the distribution contents and confirm LICENSE and NOTICE are included before publishing. Building locally does not publish a release.

For bug reports, include the version, a minimal synthetic reproduction, expected behavior and actual output. Avoid posting real prompts, credentials or customer identifiers. Security-sensitive reports follow SECURITY.md.
