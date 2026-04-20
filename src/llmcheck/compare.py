from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import run_assertion
from .models import AppConfig, CaseResult, CheckResult, LLMResponse, VariantSpec
from .providers import ProviderError, call_provider
from .runner import RunExecutionError, _collect_context_chunks
from .traces import TraceError, load_case_trace_events
from .utils import redact_text


class CompareExecutionError(Exception):
    pass


def _serialize_case_result(case: CaseResult) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "suite": case.suite,
        "provider": case.provider,
        "model": case.model,
        "passed": case.passed,
        "latency_ms": case.latency_ms,
        "error": case.error,
        "checks": [
            {
                "check_type": c.check_type,
                "passed": c.passed,
                "message": c.message,
                "details": c.details,
            }
            for c in case.checks
        ],
    }


def _extract_metric(case: CaseResult, check_type: str, key_path: list[str], default: Any = None) -> Any:
    for check in case.checks:
        if check.check_type != check_type:
            continue
        current: Any = check.details
        for key in key_path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current
    return default


def _usage_total_tokens(metadata: dict[str, Any]) -> int | None:
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    for key in ("total_tokens", "totalTokenCount", "total_token_count"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens + output_tokens
    return None


def _apply_variant(case: Any, variant: VariantSpec) -> Any:
    provider = variant.provider or case.provider
    model = variant.model or case.model
    messages = list(case.messages)
    if variant.prompt_prefix:
        messages = [{"role": "system", "content": variant.prompt_prefix}, *messages]
    return replace(case, provider=provider, model=model, messages=messages)


def _run_single_case(config: AppConfig, case: Any, repeats_override: int | None, baseline_root: Path) -> tuple[CaseResult, dict[str, Any]]:
    repeats = repeats_override if repeats_override is not None else case.repeats
    if repeats < 1:
        repeats = 1

    try:
        context_chunks = _collect_context_chunks(case)
    except RunExecutionError as exc:
        check = CheckResult(check_type="runtime", passed=False, message=redact_text(str(exc)))
        return (
            CaseResult(
                case_id=case.id,
                suite=case.suite,
                provider=case.provider,
                model=case.model,
                passed=False,
                checks=[check],
                error=redact_text(str(exc)),
            ),
            {},
        )

    try:
        trace_events = load_case_trace_events(case)
    except TraceError as exc:
        check = CheckResult(check_type="runtime", passed=False, message=redact_text(str(exc)))
        return (
            CaseResult(
                case_id=case.id,
                suite=case.suite,
                provider=case.provider,
                model=case.model,
                passed=False,
                checks=[check],
                error=redact_text(str(exc)),
            ),
            {},
        )

    responses: list[LLMResponse] = []
    runtime_error: str | None = None
    for _ in range(repeats):
        try:
            responses.append(call_provider(config, case))
        except ProviderError as exc:
            runtime_error = str(exc)
            break

    if runtime_error or not responses:
        check = CheckResult(check_type="runtime", passed=False, message=redact_text(runtime_error or "unknown runtime error"))
        return (
            CaseResult(
                case_id=case.id,
                suite=case.suite,
                provider=case.provider,
                model=case.model,
                passed=False,
                checks=[check],
                error=redact_text(runtime_error or "unknown runtime error"),
            ),
            {},
        )

    first = responses[0]
    checks: list[CheckResult] = []
    for assertion in case.assertions:
        if assertion.type == "baseline_diff":
            continue
        checks.append(
            run_assertion(
                assertion=assertion,
                first_response=first,
                responses=responses,
                suite=case.suite,
                case_id=case.id,
                baseline_root=baseline_root,
                update_baseline=False,
                context_chunks=context_chunks,
                trace_events=trace_events,
            )
        )

    passed = all(c.passed for c in checks)
    return (
        CaseResult(
            case_id=case.id,
            suite=case.suite,
            provider=case.provider,
            model=case.model,
            passed=passed,
            checks=checks,
            latency_ms=first.metadata.get("latency_ms") if isinstance(first.metadata, dict) else None,
            error=first.error,
        ),
        first.metadata,
    )


def execute_compare(
    config: AppConfig,
    cases: list[Any],
    variants: list[VariantSpec],
    repeats_override: int | None,
    baseline_root: Path,
    report_path: Path,
) -> dict[str, Any]:
    if not variants:
        raise CompareExecutionError("No variants configured for compare. Use config variants or --variant flags.")

    matrix: list[dict[str, Any]] = []
    results_by_variant: dict[str, list[dict[str, Any]]] = {}

    for variant in variants:
        per_variant: list[dict[str, Any]] = []
        for case in cases:
            variant_case = _apply_variant(case, variant)
            case_result, metadata = _run_single_case(config, variant_case, repeats_override, baseline_root)

            grounding_score = _extract_metric(case_result, "grounding_assertion", ["summary", "grounding_score"])
            unsupported_claims = _extract_metric(case_result, "grounding_assertion", ["summary", "insufficient_evidence"])
            contradicted_claims = _extract_metric(case_result, "grounding_assertion", ["summary", "contradicted"])
            tool_violations = _extract_metric(case_result, "tool_contract", ["violation_count"], 0)
            stability_score = _extract_metric(case_result, "stability", ["ratio"])
            tokens = _usage_total_tokens(metadata if isinstance(metadata, dict) else {})

            item = {
                "variant": variant.name,
                "suite": case_result.suite,
                "case_id": case_result.case_id,
                "provider": case_result.provider,
                "model": case_result.model,
                "passed": case_result.passed,
                "schema_valid": all(c.passed for c in case_result.checks if c.check_type == "schema_valid")
                if any(c.check_type == "schema_valid" for c in case_result.checks)
                else None,
                "grounding_score": grounding_score,
                "unsupported_claims": unsupported_claims,
                "contradicted_claims": contradicted_claims,
                "tool_violations": tool_violations,
                "latency_ms": case_result.latency_ms,
                "cost_estimate": {"total_tokens": tokens, "total_cost_usd": (metadata or {}).get("cost_usd") if isinstance(metadata, dict) else None},
                "stability_score": stability_score,
                "error": case_result.error,
            }
            matrix.append(item)
            per_variant.append({
                "summary": item,
                "result": _serialize_case_result(case_result),
            })
        results_by_variant[variant.name] = per_variant

    passed = all(row.get("passed") for row in matrix)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "variants": [v.name for v in variants],
        "matrix": matrix,
        "results_by_variant": results_by_variant,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path.parent.joinpath(f"compare-{stamp}.json").write_text(payload, encoding="utf-8")
    return report
