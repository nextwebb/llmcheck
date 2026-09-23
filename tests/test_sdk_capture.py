from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from llmcheck import add_context, add_tags, flag, instrument_openai
from llmcheck.pilot import build_knowledge_entry, build_pilot_review
from llmcheck.storage.sqlite import init_db, save_knowledge_entry
from llmcheck.storage.sqlite import get_run, list_runs


class FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Refunds above $100 need manager approval."))],
            usage=SimpleNamespace(total_tokens=21),
        )


class FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_instrument_openai_preserves_response_and_captures_run(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    client = FakeClient()
    wrapped = instrument_openai(client, storage_path=db_path)

    add_context(["chunk one"])
    add_tags({"session_id": "abc123"})
    response = wrapped.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a support agent."},
            {"role": "user", "content": "Can I get a refund above $100?"},
        ],
    )

    assert response.choices[0].message.content == "Refunds above $100 need manager approval."
    runs = list_runs(db_path)
    assert len(runs) == 1
    run = runs[0]
    assert run.input_json["model"] == "gpt-4o"
    assert run.input_json["user_input"] == "Can I get a refund above $100?"
    assert run.output_text == "Refunds above $100 need manager approval."
    assert run.context == [{"id": "context-1", "text": "chunk one"}]
    assert run.tags == {"session_id": "abc123"}
    assert run.metadata["usage"]["total_tokens"] == 21


def test_flag_marks_most_recent_run(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    client = instrument_openai(FakeClient(), storage_path=db_path)

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )
    flag(reason="fallback_triggered")

    run = list_runs(db_path)[0]
    assert run.flagged is True
    assert run.flag_reason == "fallback_triggered"


def test_add_context_normalizes_multiple_shapes_and_storage_override(tmp_path: Path) -> None:
    db_path = tmp_path / "custom.db"
    client = instrument_openai(FakeClient(), storage_path=db_path)

    add_context(
        [
            "chunk one",
            {"id": "policy-1", "text": "Refunds above $100 require manager approval."},
        ]
    )
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "refund details"}],
    )

    run = get_run(db_path, list_runs(db_path)[0].id)
    assert run is not None
    assert run.context == [
        {"id": "context-1", "text": "chunk one"},
        {"id": "policy-1", "text": "Refunds above $100 require manager approval."},
    ]


def test_instrument_openai_applies_approved_knowledge_to_later_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    init_db(db_path)
    client = FakeClient()
    wrapped = instrument_openai(client, storage_path=db_path)

    add_tags({"workflow": "refund-bot"})
    wrapped.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Can I get a refund above $100?"}],
    )
    source_run = list_runs(db_path)[0]
    review = build_pilot_review(
        source_run,
        severity="high",
        issue_class_guess="policy_violation",
        root_cause="missing_context",
        missing_context_subtype="missing_policy_fact",
        review_outcome="confirmed_failure",
        business_impact="high",
        candidate_knowledge_type="policy_fact",
        reviewer_note="Need the approval policy fact available for later runs.",
        reusable_pattern=True,
        knowledge_approved=True,
        approved_usage_modes=["retrieval_planning_only", "runtime_retrieval_allowed"],
    )
    entry = build_knowledge_entry(
        source_run,
        review,
        title="refund approval requirement",
        body="Refunds above $100 require manager approval and take 3-5 business days.",
        confidence="high",
    )
    save_knowledge_entry(db_path, entry)

    add_tags({"workflow": "refund-bot"})
    wrapped.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Can I get a refund above $100?"}],
    )

    latest_call = client.chat.completions.calls[-1]
    assert latest_call["messages"][0]["role"] == "system"
    assert "Reviewed retrieval-planning guidance" in latest_call["messages"][0]["content"]
    assert "Approved runtime context" in latest_call["messages"][1]["content"]
    assert "manager approval" in latest_call["messages"][1]["content"]

    latest_run = list_runs(db_path)[0]
    assert latest_run.metadata["applied_knowledge"] == [
        {
            "mode": "retrieval_planning_only",
            "entry_ids": [entry.id],
            "titles": ["refund approval requirement"],
        },
        {
            "mode": "runtime_retrieval_allowed",
            "entry_ids": [entry.id],
            "titles": ["refund approval requirement"],
        },
    ]


def test_failed_provider_attempt_consumes_context_and_tags(tmp_path, capsys):
    import pytest
    db = tmp_path / 'failure.db'
    calls = 0
    def create(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('provider fixture failure')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    client = FakeClient()
    client.chat.completions.create = create
    instrument_openai(client, storage_path=db)
    client.chat.completions.create(messages=[{'role':'user', 'content':'previous'}])
    previous = list_runs(db)[0]
    add_context(['failed-call-only'])
    add_tags({'attempt': 'failed'})
    with pytest.raises(RuntimeError, match='provider fixture failure'):
        client.chat.completions.create(messages=[{'role':'user', 'content':'fail'}])
    flag('must not flag previous')
    assert not get_run(db, previous.id).flagged
    assert 'no captured run' in capsys.readouterr().err
    client.chat.completions.create(messages=[{'role':'user', 'content':'next'}])
    next_run = list_runs(db)[0]
    assert next_run.context == [] and next_run.tags == {}


def test_storage_failure_preserves_success_and_clears_flag_target(tmp_path, monkeypatch, capsys):
    import llmcheck.sdk.openai as sdk
    db = tmp_path / 'storage-failure.db'
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    client = FakeClient()
    client.chat.completions.create = lambda **kwargs: response
    instrument_openai(client, storage_path=db)
    client.chat.completions.create(messages=[{'role':'user', 'content':'previous'}])
    previous = list_runs(db)[0]
    original = sdk.save_run
    def broken_save(*args):
        raise OSError('SENSITIVE fixture body')
    monkeypatch.setattr(sdk, 'save_run', broken_save)
    add_context(['uncaptured context'])
    add_tags({'attempt': 'uncaptured'})
    assert client.chat.completions.create(messages=[{'role':'user', 'content':'current'}]) is response
    warning = capsys.readouterr().err
    assert 'local capture failed' in warning and 'SENSITIVE' not in warning
    flag('must not flag previous')
    assert not get_run(db, previous.id).flagged
    assert 'no captured run' in capsys.readouterr().err
    monkeypatch.setattr(sdk, 'save_run', original)
    client.chat.completions.create(messages=[{'role':'user', 'content':'next'}])
    next_run = list_runs(db)[0]
    assert next_run.context == [] and next_run.tags == {}


def test_retrieval_failure_consumes_both_pending_fields(tmp_path, monkeypatch):
    import pytest
    import llmcheck.sdk.openai as sdk
    db = tmp_path / 'retrieval-failure.db'
    client = instrument_openai(FakeClient(), storage_path=db)
    original = sdk.apply_retrieval_policy
    def broken_retrieval(*args, **kwargs):
        raise OSError('retrieval unavailable')
    add_context(['first attempt'])
    add_tags({'attempt': 'first'})
    monkeypatch.setattr(sdk, 'apply_retrieval_policy', broken_retrieval)
    with pytest.raises(OSError):
        client.chat.completions.create(messages=[{'role':'user', 'content':'fail'}])
    monkeypatch.setattr(sdk, 'apply_retrieval_policy', original)
    client.chat.completions.create(messages=[{'role':'user', 'content':'next'}])
    run = list_runs(db)[0]
    assert run.context == [] and run.tags == {}
