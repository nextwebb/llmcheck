from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage.models import KnowledgeEntryRecord, PilotReviewRecord, RunRecord


ROOT_CAUSES = [
    "missing_context",
    "wrong_retrieval_target",
    "reasoning_failure_with_sufficient_context",
    "prompt_or_instruction_failure",
    "tool_or_workflow_failure",
    "policy_ambiguity",
    "acceptable_edge_case",
    "false_positive_detector",
]

MISSING_CONTEXT_SUBTYPES = [
    "missing_policy_fact",
    "missing_customer_state",
    "missing_workflow_rule",
    "missing_tool_result",
    "missing_document_section",
    "missing_disambiguation_context",
]

REVIEW_OUTCOMES = ["confirmed_failure", "false_positive", "duplicate", "acceptable_behavior"]
KNOWLEDGE_TYPES = [
    "none",
    "policy_fact",
    "workflow_fact",
    "missing_context_to_fetch",
    "retrieval_hint",
    "canonical_correction",
    "known_failure_pattern",
]
USAGE_MODES = [
    "detection_only",
    "review_assist_only",
    "retrieval_planning_only",
    "runtime_retrieval_allowed",
]
SEVERITIES = ["low", "medium", "high", "critical"]
IMPACTS = ["low", "medium", "high", "critical"]
CONFIDENCE_LEVELS = ["low", "medium", "high"]


def infer_workflow(run: RunRecord) -> str:
    for key in ("workflow", "app", "pipeline"):
        value = run.tags.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "default"


def infer_detector_sources(run: RunRecord) -> list[str]:
    sources = ["manual_flag"] if run.flagged else ["heuristic"]
    if run.context:
        sources.insert(0, "deterministic")
    return sources


def build_pilot_review(
    run: RunRecord,
    *,
    severity: str,
    root_cause: str,
    review_outcome: str,
    business_impact: str,
    candidate_knowledge_type: str,
    reviewer_note: str,
    issue_class_guess: str = "unknown",
    missing_context_subtype: str | None = None,
    reusable_pattern: bool = False,
    knowledge_approved: bool = False,
    approved_usage_modes: list[str] | None = None,
    repeat_pattern_seen_before: bool = False,
    similar_prior_incident_count: int = 0,
    time_to_review_minutes: int = 0,
    time_to_operationalize_minutes: int = 0,
    recurrence_within_14d: bool = False,
    recurrence_within_30d: bool = False,
    avoided_after_intervention: bool = False,
) -> PilotReviewRecord:
    return PilotReviewRecord(
        id=f"pilot_{uuid.uuid4().hex[:12]}",
        run_id=run.id,
        created_at=datetime.now(timezone.utc).isoformat(),
        workflow=infer_workflow(run),
        severity=severity,
        detector_sources=infer_detector_sources(run),
        issue_class_guess=issue_class_guess,
        root_cause=root_cause,
        missing_context_subtype=missing_context_subtype,
        review_outcome=review_outcome,
        reusable_pattern=reusable_pattern,
        business_impact=business_impact,
        candidate_knowledge_type=candidate_knowledge_type,
        knowledge_approved=knowledge_approved,
        approved_usage_modes=approved_usage_modes or [],
        repeat_pattern_seen_before=repeat_pattern_seen_before,
        similar_prior_incident_count=similar_prior_incident_count,
        time_to_review_minutes=time_to_review_minutes,
        time_to_operationalize_minutes=time_to_operationalize_minutes,
        recurrence_within_14d=recurrence_within_14d,
        recurrence_within_30d=recurrence_within_30d,
        avoided_after_intervention=avoided_after_intervention,
        reviewer_note=reviewer_note,
    )


def build_knowledge_entry(
    run: RunRecord,
    review: PilotReviewRecord,
    *,
    title: str,
    body: str,
    confidence: str,
) -> KnowledgeEntryRecord:
    return KnowledgeEntryRecord(
        id=f"kb_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        source_run_id=run.id,
        source_review_id=review.id,
        knowledge_type=review.candidate_knowledge_type,
        title=title,
        body=body,
        scope={
            "workflow": review.workflow,
            "issue_class": review.issue_class_guess,
            "root_cause": review.root_cause,
        },
        confidence=confidence,
        usage_modes=review.approved_usage_modes,
        status="approved" if review.knowledge_approved else "candidate",
    )


def export_scorecard(path: Path, reviews: list[PilotReviewRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "incident_id",
        "run_id",
        "reviewed_at",
        "workflow",
        "severity",
        "detector_sources",
        "issue_class_guess",
        "root_cause",
        "missing_context_subtype",
        "review_outcome",
        "reusable_pattern",
        "business_impact",
        "candidate_knowledge_type",
        "knowledge_approved",
        "approved_usage_modes",
        "repeat_pattern_seen_before",
        "similar_prior_incident_count",
        "time_to_review_minutes",
        "time_to_operationalize_minutes",
        "recurrence_within_14d",
        "recurrence_within_30d",
        "avoided_after_intervention",
        "reviewer_note",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in reviews:
            writer.writerow(
                {
                    "incident_id": item.id,
                    "run_id": item.run_id,
                    "reviewed_at": item.created_at,
                    "workflow": item.workflow,
                    "severity": item.severity,
                    "detector_sources": json.dumps(item.detector_sources, ensure_ascii=True),
                    "issue_class_guess": item.issue_class_guess,
                    "root_cause": item.root_cause,
                    "missing_context_subtype": item.missing_context_subtype or "",
                    "review_outcome": item.review_outcome,
                    "reusable_pattern": item.reusable_pattern,
                    "business_impact": item.business_impact,
                    "candidate_knowledge_type": item.candidate_knowledge_type,
                    "knowledge_approved": item.knowledge_approved,
                    "approved_usage_modes": json.dumps(item.approved_usage_modes, ensure_ascii=True),
                    "repeat_pattern_seen_before": item.repeat_pattern_seen_before,
                    "similar_prior_incident_count": item.similar_prior_incident_count,
                    "time_to_review_minutes": item.time_to_review_minutes,
                    "time_to_operationalize_minutes": item.time_to_operationalize_minutes,
                    "recurrence_within_14d": item.recurrence_within_14d,
                    "recurrence_within_30d": item.recurrence_within_30d,
                    "avoided_after_intervention": item.avoided_after_intervention,
                    "reviewer_note": item.reviewer_note,
                }
            )


def summarize_pilot(reviews: list[PilotReviewRecord]) -> dict[str, Any]:
    total = len(reviews)
    if total == 0:
        return {
            "total_reviews": 0,
            "confirmed_failures": 0,
            "missing_context_share": 0.0,
            "reusable_pattern_share": 0.0,
            "knowledge_approval_rate": 0.0,
            "repeat_pattern_share": 0.0,
            "recurrence_14d_rate": 0.0,
            "recurrence_30d_rate": 0.0,
            "root_causes": {},
        }

    confirmed = [item for item in reviews if item.review_outcome == "confirmed_failure"]
    missing_context = [item for item in confirmed if item.root_cause in {"missing_context", "wrong_retrieval_target"}]
    reusable = [item for item in confirmed if item.reusable_pattern]
    candidates = [item for item in confirmed if item.candidate_knowledge_type != "none"]
    approved = [item for item in candidates if item.knowledge_approved]
    repeated = [item for item in confirmed if item.repeat_pattern_seen_before or item.similar_prior_incident_count > 0]
    rec_14 = [item for item in confirmed if item.recurrence_within_14d]
    rec_30 = [item for item in confirmed if item.recurrence_within_30d]

    root_counts: dict[str, int] = {}
    for item in reviews:
        root_counts[item.root_cause] = root_counts.get(item.root_cause, 0) + 1

    return {
        "total_reviews": total,
        "confirmed_failures": len(confirmed),
        "missing_context_share": round(len(missing_context) / len(confirmed), 4) if confirmed else 0.0,
        "reusable_pattern_share": round(len(reusable) / len(confirmed), 4) if confirmed else 0.0,
        "knowledge_approval_rate": round(len(approved) / len(candidates), 4) if candidates else 0.0,
        "repeat_pattern_share": round(len(repeated) / len(confirmed), 4) if confirmed else 0.0,
        "recurrence_14d_rate": round(len(rec_14) / len(confirmed), 4) if confirmed else 0.0,
        "recurrence_30d_rate": round(len(rec_30) / len(confirmed), 4) if confirmed else 0.0,
        "root_causes": root_counts,
    }


def write_pilot_report(path: Path, reviews: list[PilotReviewRecord]) -> None:
    summary = summarize_pilot(reviews)
    lines = [
        f"# Pilot Report -- {datetime.now(timezone.utc).date().isoformat()}",
        "",
        f"- Total reviews: {summary['total_reviews']}",
        f"- Confirmed failures: {summary['confirmed_failures']}",
        f"- Missing context share: {summary['missing_context_share']:.0%}",
        f"- Reusable pattern share: {summary['reusable_pattern_share']:.0%}",
        f"- Knowledge approval rate: {summary['knowledge_approval_rate']:.0%}",
        f"- Repeat pattern share: {summary['repeat_pattern_share']:.0%}",
        f"- 14d recurrence rate: {summary['recurrence_14d_rate']:.0%}",
        f"- 30d recurrence rate: {summary['recurrence_30d_rate']:.0%}",
        "",
        "## Root Causes",
        "",
    ]
    for key, value in sorted(summary["root_causes"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Kill Test")
    lines.append("")
    lines.append("- If missing_context_share stays low, the knowledge loop is the wrong intervention.")
    lines.append("- If reusable_pattern_share stays low, incidents are too one-off to compound.")
    lines.append("- If knowledge_approval_rate stays low, review output is too noisy to trust.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def review_to_dict(review: PilotReviewRecord) -> dict[str, Any]:
    return asdict(review)
