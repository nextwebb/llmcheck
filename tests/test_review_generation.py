from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import yaml

from llmcheck.cli import _review_command
from llmcheck.generation import draft_regression_case, dump_regression_case
from llmcheck.storage.models import RunRecord
from llmcheck.storage.sqlite import init_db, list_runs, save_run


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "llmcheck.yaml"
    path.write_text(
        "storage:\n  path: .llmcheck/llmcheck.db\njudge:\n  provider: openai\n  model: gpt-4o-mini\n",
        encoding="utf-8",
    )
    return path


def _suite_file(tmp_path: Path) -> Path:
    path = tmp_path / "llmcheck_suite.yaml"
    path.write_text("runner:\n  type: python\n  callable: examples.rag_support_agent:answer_user\ntests: []\n", encoding="utf-8")
    return path


def _run_record() -> RunRecord:
    return RunRecord(
        id="run_123",
        created_at="2026-05-25T14:30:00Z",
        input_json={"user_input": "Can I get a refund above $100?", "model": "gpt-4o"},
        output_text="Yes, the refund is instant.",
        messages=[{"role": "user", "content": "Can I get a refund above $100?"}],
        context=[{"id": "policy-1", "text": "Refunds above $100 require manager approval and take 3-5 business days."}],
        tags={"session_id": "abc123"},
        metadata={"model": "gpt-4o"},
        flagged=True,
        flag_reason="fallback_triggered",
    )


def test_draft_generation_produces_yaml_with_required_fields() -> None:
    draft = draft_regression_case(_run_record(), 'Mention manager approval and avoid "instant".')
    text = dump_regression_case(draft)
    payload = yaml.safe_load(text)
    assert payload["source_run_id"] == "run_123"
    assert payload["expected"]["must_include"] == ['Mention manager approval and avoid "instant".']
    assert payload["expected"]["must_not_claim"] == ["instant"]
    assert payload["judge"]["pass_if"]


def test_approved_review_appends_to_suite(monkeypatch, tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    suite_path = _suite_file(tmp_path)
    db_path = tmp_path / ".llmcheck" / "llmcheck.db"
    init_db(db_path)
    save_run(db_path, _run_record())

    answers = iter(["Mention manager approval and avoid \"instant\".", "a"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    code = _review_command(Namespace(config=str(config_path), run_id="run_123", latest=False, suite=str(suite_path)))
    assert code == 0
    payload = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    assert len(payload["tests"]) == 1
    assert payload["tests"][0]["source_run_id"] == "run_123"


def test_rejected_review_does_not_append_to_suite(monkeypatch, tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    suite_path = _suite_file(tmp_path)
    db_path = tmp_path / ".llmcheck" / "llmcheck.db"
    init_db(db_path)
    save_run(db_path, _run_record())

    answers = iter(["Mention manager approval and avoid \"instant\".", "r"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    code = _review_command(Namespace(config=str(config_path), run_id="run_123", latest=False, suite=str(suite_path)))
    assert code == 0
    payload = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    assert payload["tests"] == []
