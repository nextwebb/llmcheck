from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from llmcheck.cli import _pilot_knowledge_command, _pilot_report_command, _pilot_review_command, _pilot_scorecard_command
from llmcheck.pilot import build_pilot_review, summarize_pilot
from llmcheck.storage.models import RunRecord
from llmcheck.storage.sqlite import (
    get_run,
    init_db,
    list_knowledge_entries,
    list_pilot_reviews,
    save_pilot_review,
    save_run,
)


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "llmcheck.yaml"
    path.write_text(
        "storage:\n  path: .llmcheck/llmcheck.db\njudge:\n  provider: openai\n  model: gpt-4o-mini\n",
        encoding="utf-8",
    )
    return path


def _run_record() -> RunRecord:
    return RunRecord(
        id="run_123",
        created_at="2026-05-25T14:30:00Z",
        input_json={"user_input": "Can I get a refund above $100?", "model": "gpt-4o"},
        output_text="Yes, the refund is instant.",
        messages=[{"role": "user", "content": "Can I get a refund above $100?"}],
        context=[{"id": "policy-1", "text": "Refunds above $100 require manager approval and take 3-5 business days."}],
        tags={"workflow": "refund-bot"},
        metadata={"model": "gpt-4o"},
        flagged=True,
        flag_reason="claimed instant refund",
    )


def test_build_pilot_review_summary() -> None:
    review = build_pilot_review(
        _run_record(),
        severity="high",
        root_cause="missing_context",
        missing_context_subtype="missing_policy_fact",
        review_outcome="confirmed_failure",
        business_impact="high",
        candidate_knowledge_type="policy_fact",
        reviewer_note="Need policy threshold facts.",
        issue_class_guess="policy_violation",
        reusable_pattern=True,
        knowledge_approved=True,
        approved_usage_modes=["review_assist_only", "retrieval_planning_only"],
        repeat_pattern_seen_before=True,
        similar_prior_incident_count=2,
        recurrence_within_14d=True,
    )
    summary = summarize_pilot([review])
    assert summary["confirmed_failures"] == 1
    assert summary["missing_context_share"] == 1.0
    assert summary["knowledge_approval_rate"] == 1.0


def test_pilot_review_command_persists_review_and_knowledge(monkeypatch, tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    db_path = tmp_path / ".llmcheck" / "llmcheck.db"
    init_db(db_path)
    save_run(db_path, _run_record())

    answers = iter(
        [
            "high",
            "policy_violation",
            "missing_context",
            "missing_policy_fact",
            "confirmed_failure",
            "y",
            "high",
            "policy_fact",
            "y",
            "review_assist_only,retrieval_planning_only",
            "y",
            "2",
            "7",
            "12",
            "y",
            "n",
            "n",
            "Need the approval policy fact in retrieval.",
            "refund approval requirement",
            "Refunds above $100 require manager approval and take 3-5 business days.",
            "high",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    code = _pilot_review_command(Namespace(config=str(config_path), run_id="run_123", latest=False))
    assert code == 0
    reviews = list_pilot_reviews(db_path)
    entries = list_knowledge_entries(db_path)
    assert len(reviews) == 1
    assert reviews[0].root_cause == "missing_context"
    assert reviews[0].knowledge_approved is True
    assert len(entries) == 1
    assert entries[0].knowledge_type == "policy_fact"
    assert entries[0].scope["workflow"] == "refund-bot"


def test_pilot_scorecard_and_report_generation(tmp_path: Path, capsys) -> None:
    config_path = _config_file(tmp_path)
    db_path = tmp_path / ".llmcheck" / "llmcheck.db"
    init_db(db_path)
    save_run(db_path, _run_record())
    save_pilot_review(
        db_path,
        build_pilot_review(
            get_run(db_path, "run_123"),
            severity="high",
            root_cause="missing_context",
            missing_context_subtype="missing_policy_fact",
            review_outcome="confirmed_failure",
            business_impact="high",
            candidate_knowledge_type="policy_fact",
            reviewer_note="Need policy fact.",
            issue_class_guess="policy_violation",
            reusable_pattern=True,
            knowledge_approved=True,
            approved_usage_modes=["review_assist_only"],
            repeat_pattern_seen_before=True,
            similar_prior_incident_count=3,
            recurrence_within_14d=True,
            recurrence_within_30d=True,
        ),
    )

    scorecard_path = tmp_path / "scorecard.csv"
    report_path = tmp_path / "pilot.md"

    assert _pilot_scorecard_command(Namespace(config=str(config_path), output=str(scorecard_path), limit=100)) == 0
    assert "incident_id" in scorecard_path.read_text(encoding="utf-8")

    assert _pilot_report_command(Namespace(config=str(config_path), output=str(report_path), limit=100)) == 0
    report_text = report_path.read_text(encoding="utf-8")
    assert "Missing context share" in report_text
    assert "Kill Test" in report_text

    assert _pilot_knowledge_command(Namespace(config=str(config_path), limit=100)) == 0
    output = capsys.readouterr().out
    assert "knowledge_id | created_at" in output
