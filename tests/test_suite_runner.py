from __future__ import annotations

from pathlib import Path

import pytest

from llmcheck.config import load_config
from llmcheck.suite_runner import SuiteRunError, import_callable, run_suite


def _write_module(tmp_path: Path) -> None:
    (tmp_path / "fakeapp.py").write_text(
        "def answer_user(query):\n"
        "    return f'Response: {query}'\n",
        encoding="utf-8",
    )


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "llmcheck.yaml"
    config_path.write_text(
        "storage:\n  path: .llmcheck/llmcheck.db\njudge:\n  provider: openai\n  model: gpt-4o-mini\n",
        encoding="utf-8",
    )
    return config_path


def test_import_callable_from_string(tmp_path: Path, monkeypatch) -> None:
    _write_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    func = import_callable("fakeapp:answer_user")
    assert func(query="hello") == "Response: hello"


def test_import_callable_uses_suite_working_directory(tmp_path: Path) -> None:
    _write_module(tmp_path)
    func = import_callable("fakeapp:answer_user", working_dir=tmp_path)
    assert func(query="hello") == "Response: hello"


def test_run_suite_passes_when_judge_returns_no_violations(tmp_path: Path, monkeypatch) -> None:
    _write_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    suite_path = tmp_path / "llmcheck_suite.yaml"
    suite_path.write_text(
        """
runner:
  type: python
  callable: "fakeapp:answer_user"
tests:
  - id: refund_policy
    source_run_id: "run_123"
    source_reason: "bad output"
    metadata:
      created_at: "2026-05-25T14:30:00Z"
      reviewed_by: "local"
    inputs:
      query: "hello"
    context:
      - id: "policy-1"
        text: "context"
    expected:
      must_include: ["hello"]
      must_not_claim: []
    judge:
      type: rubric
      pass_if: "say hello"
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(_write_config(tmp_path))
    result = run_suite(
        config,
        suite_path,
        judge_transport=lambda _config, _prompt: '{"missing_requirements":[],"forbidden_claims_found":[],"unsupported_claims":[],"reason":"ok","confidence":"high"}',
    )
    assert result.passed is True
    assert result.results[0].passed is True


def test_run_suite_fails_when_judge_returns_violations(tmp_path: Path, monkeypatch) -> None:
    _write_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    suite_path = tmp_path / "llmcheck_suite.yaml"
    suite_path.write_text(
        """
runner:
  type: python
  callable: "fakeapp:answer_user"
tests:
  - id: refund_policy
    source_run_id: "run_123"
    source_reason: "bad output"
    metadata:
      created_at: "2026-05-25T14:30:00Z"
      reviewed_by: "local"
    inputs:
      query: "hello"
    context:
      - id: "policy-1"
        text: "context"
    expected:
      must_include: ["manager approval"]
      must_not_claim: ["instant"]
    judge:
      type: rubric
      pass_if: "say manager approval"
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(_write_config(tmp_path))
    result = run_suite(
        config,
        suite_path,
        judge_transport=lambda _config, _prompt: '{"missing_requirements":["manager approval"],"forbidden_claims_found":[],"unsupported_claims":[],"reason":"missing","confidence":"high"}',
    )
    assert result.passed is False
    assert result.results[0].passed is False


def test_invalid_callable_exits_as_runtime_error(tmp_path: Path) -> None:
    suite_path = tmp_path / "llmcheck_suite.yaml"
    suite_path.write_text(
        """
runner:
  type: python
  callable: "fakeapp:missing"
tests: []
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    config = load_config(_write_config(tmp_path))
    with pytest.raises(SuiteRunError, match="callable `missing` not found in `fakeapp`"):
        run_suite(config, suite_path, judge_transport=lambda _config, _prompt: "")


def test_malformed_yaml_exits_as_runtime_error(tmp_path: Path) -> None:
    suite_path = tmp_path / "llmcheck_suite.yaml"
    suite_path.write_text("runner: [", encoding="utf-8")
    config = load_config(_write_config(tmp_path))
    with pytest.raises(Exception):
        run_suite(config, suite_path, judge_transport=lambda _config, _prompt: "")
