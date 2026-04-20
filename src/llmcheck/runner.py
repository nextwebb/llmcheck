from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import run_assertion
from .config import AppConfig, ConfigError, load_cases
from .models import CaseResult, CheckResult, LLMResponse, RunResult
from .providers import ProviderError, call_provider
from .traces import TraceError, load_case_trace_events
from .utils import redact_text


class RunExecutionError(Exception):
    pass


def _collect_context_chunks(case: Any) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for idx, chunk in enumerate(case.context_chunks):
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        chunk_id = chunk.get("id") or f"chunk-{idx + 1}"
        chunks.append({"id": str(chunk_id), "text": text})

    next_idx = len(chunks) + 1
    for path in case.context_files:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise RunExecutionError(f"context file not found: {path}") from exc
        if not text:
            continue
        chunks.append({"id": f"file-{next_idx}", "text": text, "source": str(path)})
        next_idx += 1

    return chunks


def _report_counts(result_map: dict[str, list[CaseResult]]) -> dict[str, int]:
    total_cases = 0
    passed_cases = 0
    failed_cases = 0
    total_checks = 0
    failed_checks = 0
    runtime_error_cases = 0
    for cases in result_map.values():
        for case in cases:
            total_cases += 1
            if case.passed:
                passed_cases += 1
            else:
                failed_cases += 1
            total_checks += len(case.checks)
            failed_checks += sum(1 for c in case.checks if not c.passed)
            if case.error:
                runtime_error_cases += 1

    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "total_checks": total_checks,
        "failed_checks": failed_checks,
        "runtime_error_cases": runtime_error_cases,
    }


def _serialize_run(run: RunResult) -> dict[str, Any]:
    data: dict[str, Any] = {
        "passed": run.passed,
        "counts": run.counts,
        "suites": {},
    }
    for suite, cases in run.suites.items():
        data["suites"][suite] = [asdict(case) for case in cases]
    return data


def _write_json_report(path: Path, run: RunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_serialize_run(run), indent=2, ensure_ascii=True) + "\n"
    path.write_text(payload, encoding="utf-8")

    # Keep a timestamped copy to make local dashboard inspection easier.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history_path = path.parent / f"report-{stamp}.json"
    history_path.write_text(payload, encoding="utf-8")


def _case_failure(case_id: str, suite: str, provider: str, model: str, message: str) -> CaseResult:
    check = CheckResult(check_type="runtime", passed=False, message=redact_text(message))
    return CaseResult(
        case_id=case_id,
        suite=suite,
        provider=provider,
        model=model,
        passed=False,
        checks=[check],
        error=redact_text(message),
    )


def execute_run(
    config: AppConfig,
    suite_filter: str | None,
    repeats_override: int | None,
    update_baseline: bool,
    report_path: Path,
    baseline_root: Path,
    diff_mode: bool = False,
) -> RunResult:
    try:
        cases = load_cases(config, suite_filter)
    except ConfigError as exc:
        raise RunExecutionError(str(exc)) from exc

    suite_results: dict[str, list[CaseResult]] = {}

    for case in cases:
        repeats = repeats_override if repeats_override is not None else case.repeats
        if repeats < 1:
            repeats = 1

        responses: list[LLMResponse] = []
        runtime_error: str | None = None
        try:
            context_chunks = _collect_context_chunks(case)
        except RunExecutionError as exc:
            runtime_error = str(exc)
            context_chunks = []
        try:
            trace_events = load_case_trace_events(case)
        except TraceError as exc:
            runtime_error = str(exc)
            trace_events = []

        if runtime_error:
            case_result = _case_failure(case.id, case.suite, case.provider, case.model, runtime_error)
            suite_results.setdefault(case.suite, []).append(case_result)
            continue

        for _ in range(repeats):
            try:
                responses.append(call_provider(config, case))
            except ProviderError as exc:
                runtime_error = str(exc)
                break

        if runtime_error or not responses:
            case_result = _case_failure(case.id, case.suite, case.provider, case.model, runtime_error or "unknown runtime error")
            suite_results.setdefault(case.suite, []).append(case_result)
            continue

        first = responses[0]
        checks: list[CheckResult] = []

        for assertion in case.assertions:
            if diff_mode and assertion.type != "baseline_diff":
                continue
            checks.append(
                run_assertion(
                    assertion=assertion,
                    first_response=first,
                    responses=responses,
                    suite=case.suite,
                    case_id=case.id,
                    baseline_root=baseline_root,
                    update_baseline=update_baseline,
                    context_chunks=context_chunks,
                    trace_events=trace_events,
                )
            )

        if not checks and diff_mode:
            checks.append(CheckResult(check_type="baseline_diff", passed=True, message="no baseline_diff assertion in case; skipped"))

        passed = all(c.passed for c in checks)
        case_result = CaseResult(
            case_id=case.id,
            suite=case.suite,
            provider=case.provider,
            model=case.model,
            passed=passed,
            checks=checks,
            latency_ms=first.metadata.get("latency_ms") if isinstance(first.metadata, dict) else None,
            error=first.error,
        )
        suite_results.setdefault(case.suite, []).append(case_result)

    counts = _report_counts(suite_results)
    run = RunResult(
        passed=counts["failed_cases"] == 0,
        suites=suite_results,
        counts=counts,
    )
    _write_json_report(report_path, run)
    return run
