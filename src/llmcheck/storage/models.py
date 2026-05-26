from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunRecord:
    id: str
    created_at: str
    input_json: dict[str, Any]
    output_text: str
    messages: list[dict[str, Any]]
    context: list[dict[str, Any]] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    flagged: bool = False
    flag_reason: str | None = None
    name: str | None = None


@dataclass
class ReviewRecord:
    id: str
    run_id: str
    created_at: str
    correction_text: str
    generated_yaml: str
    status: str


@dataclass
class PilotReviewRecord:
    id: str
    run_id: str
    created_at: str
    workflow: str
    severity: str
    detector_sources: list[str]
    issue_class_guess: str
    root_cause: str
    missing_context_subtype: str | None
    review_outcome: str
    reusable_pattern: bool
    business_impact: str
    candidate_knowledge_type: str
    knowledge_approved: bool
    approved_usage_modes: list[str]
    repeat_pattern_seen_before: bool
    similar_prior_incident_count: int
    time_to_review_minutes: int
    time_to_operationalize_minutes: int
    recurrence_within_14d: bool
    recurrence_within_30d: bool
    avoided_after_intervention: bool
    reviewer_note: str = ""


@dataclass
class KnowledgeEntryRecord:
    id: str
    created_at: str
    source_run_id: str
    source_review_id: str
    knowledge_type: str
    title: str
    body: str
    scope: dict[str, Any]
    confidence: str
    usage_modes: list[str]
    status: str


@dataclass
class StorageConfig:
    path: Path


@dataclass
class JudgeConfig:
    provider: str
    model: str


@dataclass
class AppConfig:
    root_dir: Path
    storage: StorageConfig
    judge: JudgeConfig


@dataclass
class SuiteRunnerConfig:
    type: str
    callable: str


@dataclass
class SuiteTestCase:
    id: str
    source_run_id: str
    source_reason: str
    metadata: dict[str, Any]
    inputs: dict[str, Any]
    context: list[dict[str, Any]]
    expected: dict[str, list[str]]
    judge: dict[str, Any]


@dataclass
class SuiteSpec:
    runner: SuiteRunnerConfig
    tests: list[SuiteTestCase]


@dataclass
class JudgeResult:
    missing_requirements: list[str]
    forbidden_claims_found: list[str]
    unsupported_claims: list[str]
    reason: str
    confidence: str


@dataclass
class SuiteTestResult:
    test_id: str
    passed: bool
    judge_result: JudgeResult


@dataclass
class SuiteRunResult:
    passed: bool
    results: list[SuiteTestResult]
