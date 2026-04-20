from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AssertionSpec:
    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptPolicy:
    reasoning_level: str = "medium"
    allow_planning: bool = True
    sparring_mode: bool = True
    conversational_style: bool = False
    unpredictable_style: bool = False


@dataclass
class CaseSpec:
    id: str
    suite: str
    provider: str
    model: str
    messages: list[dict[str, str]]
    assertions: list[AssertionSpec]
    path: Path
    context_files: list[Path] = field(default_factory=list)
    context_chunks: list[dict[str, Any]] = field(default_factory=list)
    trace_file: Path | None = None
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    baseline_enabled: bool = True
    repeats: int = 1
    policy: PromptPolicy = field(default_factory=PromptPolicy)


@dataclass
class SuiteSpec:
    name: str
    case_globs: list[str]


@dataclass
class VariantSpec:
    name: str
    provider: str | None = None
    model: str | None = None
    prompt_prefix: str | None = None


@dataclass
class ProviderConfig:
    api_key_env: str
    base_url: str | None = None


@dataclass
class AppConfig:
    root_dir: Path
    providers: dict[str, ProviderConfig]
    suites: list[SuiteSpec]
    variants: list[VariantSpec] = field(default_factory=list)


@dataclass
class LLMResponse:
    text: str
    structured: Any
    metadata: dict[str, Any]
    error: str | None = None


@dataclass
class CheckResult:
    check_type: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    case_id: str
    suite: str
    provider: str
    model: str
    passed: bool
    checks: list[CheckResult]
    latency_ms: int | None = None
    error: str | None = None


@dataclass
class RunResult:
    passed: bool
    suites: dict[str, list[CaseResult]]
    counts: dict[str, int]
