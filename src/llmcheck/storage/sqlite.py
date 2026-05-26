from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import KnowledgeEntryRecord, PilotReviewRecord, ReviewRecord, RunRecord


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect(path: Path) -> sqlite3.Connection:
    _ensure_parent(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path) -> None:
    with _connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY,
              name TEXT,
              created_at TEXT NOT NULL,
              input_json TEXT NOT NULL,
              output_text TEXT,
              messages_json TEXT,
              context_json TEXT,
              tags_json TEXT,
              metadata_json TEXT,
              flagged INTEGER DEFAULT 0,
              flag_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              correction_text TEXT NOT NULL,
              generated_yaml TEXT NOT NULL,
              status TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_reviews (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              workflow TEXT NOT NULL,
              severity TEXT NOT NULL,
              detector_sources_json TEXT NOT NULL,
              issue_class_guess TEXT NOT NULL,
              root_cause TEXT NOT NULL,
              missing_context_subtype TEXT,
              review_outcome TEXT NOT NULL,
              reusable_pattern INTEGER NOT NULL,
              business_impact TEXT NOT NULL,
              candidate_knowledge_type TEXT NOT NULL,
              knowledge_approved INTEGER NOT NULL,
              approved_usage_modes_json TEXT NOT NULL,
              repeat_pattern_seen_before INTEGER NOT NULL,
              similar_prior_incident_count INTEGER NOT NULL,
              time_to_review_minutes INTEGER NOT NULL,
              time_to_operationalize_minutes INTEGER NOT NULL,
              recurrence_within_14d INTEGER NOT NULL,
              recurrence_within_30d INTEGER NOT NULL,
              avoided_after_intervention INTEGER NOT NULL,
              reviewer_note TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_entries (
              id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              source_run_id TEXT NOT NULL,
              source_review_id TEXT NOT NULL,
              knowledge_type TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              scope_json TEXT NOT NULL,
              confidence TEXT NOT NULL,
              usage_modes_json TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_run(path: Path, run: RunRecord) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
              id, name, created_at, input_json, output_text, messages_json,
              context_json, tags_json, metadata_json, flagged, flag_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.name,
                run.created_at,
                json.dumps(run.input_json, ensure_ascii=True),
                run.output_text,
                json.dumps(run.messages, ensure_ascii=True),
                json.dumps(run.context, ensure_ascii=True),
                json.dumps(run.tags, ensure_ascii=True),
                json.dumps(run.metadata, ensure_ascii=True),
                int(run.flagged),
                run.flag_reason,
            ),
        )
        conn.commit()


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        input_json=json.loads(row["input_json"]),
        output_text=row["output_text"] or "",
        messages=json.loads(row["messages_json"] or "[]"),
        context=json.loads(row["context_json"] or "[]"),
        tags=json.loads(row["tags_json"] or "{}"),
        metadata=json.loads(row["metadata_json"] or "{}"),
        flagged=bool(row["flagged"]),
        flag_reason=row["flag_reason"],
    )


def list_runs(path: Path, flagged: bool = False, limit: int = 20) -> list[RunRecord]:
    init_db(path)
    query = """
        SELECT * FROM runs
        {where}
        ORDER BY created_at DESC
        LIMIT ?
    """
    where = "WHERE flagged = 1" if flagged else ""
    with _connect(path) as conn:
        rows = conn.execute(query.format(where=where), (limit,)).fetchall()
    return [_row_to_run(row) for row in rows]


def get_run(path: Path, run_id: str) -> RunRecord | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def mark_run_flagged(path: Path, run_id: str, reason: str) -> bool:
    init_db(path)
    with _connect(path) as conn:
        cur = conn.execute(
            "UPDATE runs SET flagged = 1, flag_reason = ? WHERE id = ?",
            (reason, run_id),
        )
        conn.commit()
    return cur.rowcount > 0


def save_review(path: Path, review: ReviewRecord) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reviews (
              id, run_id, created_at, correction_text, generated_yaml, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                review.id,
                review.run_id,
                review.created_at,
                review.correction_text,
                review.generated_yaml,
                review.status,
            ),
        )
        conn.commit()


def save_pilot_review(path: Path, review: PilotReviewRecord) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pilot_reviews (
              id, run_id, created_at, workflow, severity, detector_sources_json,
              issue_class_guess, root_cause, missing_context_subtype, review_outcome,
              reusable_pattern, business_impact, candidate_knowledge_type,
              knowledge_approved, approved_usage_modes_json, repeat_pattern_seen_before,
              similar_prior_incident_count, time_to_review_minutes,
              time_to_operationalize_minutes, recurrence_within_14d,
              recurrence_within_30d, avoided_after_intervention, reviewer_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.id,
                review.run_id,
                review.created_at,
                review.workflow,
                review.severity,
                json.dumps(review.detector_sources, ensure_ascii=True),
                review.issue_class_guess,
                review.root_cause,
                review.missing_context_subtype,
                review.review_outcome,
                int(review.reusable_pattern),
                review.business_impact,
                review.candidate_knowledge_type,
                int(review.knowledge_approved),
                json.dumps(review.approved_usage_modes, ensure_ascii=True),
                int(review.repeat_pattern_seen_before),
                review.similar_prior_incident_count,
                review.time_to_review_minutes,
                review.time_to_operationalize_minutes,
                int(review.recurrence_within_14d),
                int(review.recurrence_within_30d),
                int(review.avoided_after_intervention),
                review.reviewer_note,
            ),
        )
        conn.commit()


def _row_to_pilot_review(row: sqlite3.Row) -> PilotReviewRecord:
    return PilotReviewRecord(
        id=row["id"],
        run_id=row["run_id"],
        created_at=row["created_at"],
        workflow=row["workflow"],
        severity=row["severity"],
        detector_sources=json.loads(row["detector_sources_json"]),
        issue_class_guess=row["issue_class_guess"],
        root_cause=row["root_cause"],
        missing_context_subtype=row["missing_context_subtype"],
        review_outcome=row["review_outcome"],
        reusable_pattern=bool(row["reusable_pattern"]),
        business_impact=row["business_impact"],
        candidate_knowledge_type=row["candidate_knowledge_type"],
        knowledge_approved=bool(row["knowledge_approved"]),
        approved_usage_modes=json.loads(row["approved_usage_modes_json"]),
        repeat_pattern_seen_before=bool(row["repeat_pattern_seen_before"]),
        similar_prior_incident_count=int(row["similar_prior_incident_count"]),
        time_to_review_minutes=int(row["time_to_review_minutes"]),
        time_to_operationalize_minutes=int(row["time_to_operationalize_minutes"]),
        recurrence_within_14d=bool(row["recurrence_within_14d"]),
        recurrence_within_30d=bool(row["recurrence_within_30d"]),
        avoided_after_intervention=bool(row["avoided_after_intervention"]),
        reviewer_note=row["reviewer_note"],
    )


def list_pilot_reviews(path: Path, limit: int = 200) -> list[PilotReviewRecord]:
    init_db(path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM pilot_reviews ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_pilot_review(row) for row in rows]


def save_knowledge_entry(path: Path, entry: KnowledgeEntryRecord) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO knowledge_entries (
              id, created_at, source_run_id, source_review_id, knowledge_type,
              title, body, scope_json, confidence, usage_modes_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.created_at,
                entry.source_run_id,
                entry.source_review_id,
                entry.knowledge_type,
                entry.title,
                entry.body,
                json.dumps(entry.scope, ensure_ascii=True),
                entry.confidence,
                json.dumps(entry.usage_modes, ensure_ascii=True),
                entry.status,
            ),
        )
        conn.commit()


def _row_to_knowledge_entry(row: sqlite3.Row) -> KnowledgeEntryRecord:
    return KnowledgeEntryRecord(
        id=row["id"],
        created_at=row["created_at"],
        source_run_id=row["source_run_id"],
        source_review_id=row["source_review_id"],
        knowledge_type=row["knowledge_type"],
        title=row["title"],
        body=row["body"],
        scope=json.loads(row["scope_json"]),
        confidence=row["confidence"],
        usage_modes=json.loads(row["usage_modes_json"]),
        status=row["status"],
    )


def list_knowledge_entries(path: Path, limit: int = 200) -> list[KnowledgeEntryRecord]:
    init_db(path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_knowledge_entry(row) for row in rows]


def _tokenize(value: str) -> set[str]:
    import re

    return {item for item in re.findall(r"[a-zA-Z0-9']+", value.lower()) if len(item) > 2}


def find_applicable_knowledge_entries(
    path: Path,
    *,
    workflow: str | None,
    query_text: str,
    usage_mode: str,
    limit: int = 5,
) -> list[KnowledgeEntryRecord]:
    items = list_knowledge_entries(path, limit=500)
    query_tokens = _tokenize(query_text)
    scored: list[tuple[float, KnowledgeEntryRecord]] = []
    for item in items:
        if item.status != "approved":
            continue
        if usage_mode not in item.usage_modes:
            continue
        scope_workflow = str(item.scope.get("workflow") or "").strip()
        if workflow and scope_workflow and scope_workflow != workflow:
            continue
        blob = " ".join(
            [
                item.title,
                item.body,
                str(item.scope.get("issue_class", "")),
                str(item.scope.get("root_cause", "")),
            ]
        )
        item_tokens = _tokenize(blob)
        overlap = len(query_tokens & item_tokens)
        score = overlap / max(len(query_tokens), 1)
        if score <= 0:
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].created_at))
    return [item for _, item in scored[:limit]]
