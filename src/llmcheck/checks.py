from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import AssertionSpec, CheckResult, LLMResponse
from .utils import json_path_get, maybe_parse_json, normalize_output


class CheckRuntimeError(Exception):
    pass


def _ensure_json_payload(response: LLMResponse) -> Any:
    if response.structured is not None:
        return response.structured
    parsed = maybe_parse_json(response.text)
    if parsed is None:
        raise CheckRuntimeError("Output is not valid JSON")
    return parsed


def _validate_schema_subset(schema: dict[str, Any], payload: Any, prefix: str = "$") -> list[str]:
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(payload, dict):
        return [f"{prefix}: expected object"]
    if expected_type == "array" and not isinstance(payload, list):
        return [f"{prefix}: expected array"]
    if expected_type == "string" and not isinstance(payload, str):
        return [f"{prefix}: expected string"]
    if expected_type == "number" and not isinstance(payload, (int, float)):
        return [f"{prefix}: expected number"]
    if expected_type == "integer" and not isinstance(payload, int):
        return [f"{prefix}: expected integer"]
    if expected_type == "boolean" and not isinstance(payload, bool):
        return [f"{prefix}: expected boolean"]

    if isinstance(payload, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in payload:
                    errors.append(f"{prefix}.{key}: missing required field")

        props = schema.get("properties", {})
        if isinstance(props, dict):
            for key, sub_schema in props.items():
                if key in payload and isinstance(sub_schema, dict):
                    errors.extend(_validate_schema_subset(sub_schema, payload[key], f"{prefix}.{key}"))

    if isinstance(payload, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(payload):
                errors.extend(_validate_schema_subset(item_schema, item, f"{prefix}[{idx}]"))

    return errors


def check_schema_valid(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    schema = params.get("schema")
    if not isinstance(schema, dict):
        return CheckResult("schema_valid", False, "schema_valid requires `schema` object")
    try:
        payload = _ensure_json_payload(response)
    except CheckRuntimeError as exc:
        return CheckResult("schema_valid", False, str(exc))

    errors = _validate_schema_subset(schema, payload)
    if errors:
        return CheckResult("schema_valid", False, "; ".join(errors[:3]), {"errors": errors[:20]})
    return CheckResult("schema_valid", True, "schema check passed")


def check_required_fields(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    fields = params.get("fields")
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        return CheckResult("required_fields", False, "required_fields needs `fields` string list")
    try:
        payload = _ensure_json_payload(response)
    except CheckRuntimeError as exc:
        return CheckResult("required_fields", False, str(exc))

    missing: list[str] = []
    for path in fields:
        try:
            json_path_get(payload, path)
        except KeyError:
            missing.append(path)

    if missing:
        return CheckResult("required_fields", False, f"missing fields: {', '.join(missing)}", {"missing": missing})
    return CheckResult("required_fields", True, "all required fields present")


def check_forbidden_fields(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    fields = params.get("fields")
    if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
        return CheckResult("forbidden_fields", False, "forbidden_fields needs `fields` string list")
    try:
        payload = _ensure_json_payload(response)
    except CheckRuntimeError as exc:
        return CheckResult("forbidden_fields", False, str(exc))

    present: list[str] = []
    for path in fields:
        try:
            json_path_get(payload, path)
            present.append(path)
        except KeyError:
            continue

    if present:
        return CheckResult("forbidden_fields", False, f"forbidden fields present: {', '.join(present)}", {"present": present})
    return CheckResult("forbidden_fields", True, "no forbidden fields present")


def check_regex_must_match(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    pattern = params.get("pattern")
    flags = re.IGNORECASE if params.get("ignore_case") else 0
    if not isinstance(pattern, str) or not pattern:
        return CheckResult("regex_must_match", False, "regex_must_match needs `pattern`")
    if re.search(pattern, response.text, flags=flags):
        return CheckResult("regex_must_match", True, "regex matched")
    return CheckResult("regex_must_match", False, "regex did not match", {"pattern": pattern})


def check_regex_must_not_match(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    pattern = params.get("pattern")
    flags = re.IGNORECASE if params.get("ignore_case") else 0
    if not isinstance(pattern, str) or not pattern:
        return CheckResult("regex_must_not_match", False, "regex_must_not_match needs `pattern`")
    if re.search(pattern, response.text, flags=flags):
        return CheckResult("regex_must_not_match", False, "regex unexpectedly matched", {"pattern": pattern})
    return CheckResult("regex_must_not_match", True, "regex absent as expected")


def check_json_path_equals(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    path = params.get("path")
    expected = params.get("value")
    if not isinstance(path, str) or not path:
        return CheckResult("json_path_equals", False, "json_path_equals needs `path`")
    try:
        payload = _ensure_json_payload(response)
        actual = json_path_get(payload, path)
    except (CheckRuntimeError, KeyError) as exc:
        return CheckResult("json_path_equals", False, str(exc), {"path": path})

    if actual == expected:
        return CheckResult("json_path_equals", True, "json path matched expected value")
    return CheckResult(
        "json_path_equals",
        False,
        f"json path mismatch at `{path}`",
        {"expected": expected, "actual": actual},
    )


def check_json_path_in(response: LLMResponse, params: dict[str, Any]) -> CheckResult:
    path = params.get("path")
    options = params.get("options")
    if not isinstance(path, str) or not path:
        return CheckResult("json_path_in", False, "json_path_in needs `path`")
    if not isinstance(options, list):
        return CheckResult("json_path_in", False, "json_path_in needs `options` list")

    try:
        payload = _ensure_json_payload(response)
        actual = json_path_get(payload, path)
    except (CheckRuntimeError, KeyError) as exc:
        return CheckResult("json_path_in", False, str(exc), {"path": path})

    if actual in options:
        return CheckResult("json_path_in", True, "json path value accepted")
    return CheckResult("json_path_in", False, f"value at `{path}` not in allowed options", {"actual": actual, "options": options})


def _baseline_file(baseline_root: Path, suite: str, case_id: str) -> Path:
    return baseline_root / suite / f"{case_id}.json"


def check_baseline_diff(
    response: LLMResponse,
    suite: str,
    case_id: str,
    baseline_root: Path,
    update_baseline: bool,
) -> CheckResult:
    path = _baseline_file(baseline_root, suite, case_id)
    current = normalize_output(response.text, response.structured)

    if update_baseline:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return CheckResult("baseline_diff", True, "baseline updated", {"path": str(path)})

    if not path.exists():
        return CheckResult("baseline_diff", False, "baseline missing; run with --update-baseline", {"path": str(path)})

    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return CheckResult("baseline_diff", False, "baseline file is invalid JSON", {"path": str(path)})

    if baseline == current:
        return CheckResult("baseline_diff", True, "output matches baseline")

    return CheckResult(
        "baseline_diff",
        False,
        "output differs from baseline",
        {
            "baseline": baseline,
            "current": current,
            "path": str(path),
        },
    )


def check_stability(responses: list[LLMResponse], params: dict[str, Any]) -> CheckResult:
    threshold = params.get("threshold", 1.0)
    if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
        return CheckResult("stability", False, "stability threshold must be between 0 and 1")

    if not responses:
        return CheckResult("stability", False, "no responses captured for stability")

    normalized = [normalize_output(r.text, r.structured) for r in responses]
    baseline = normalized[0]
    matches = sum(1 for item in normalized if item == baseline)
    ratio = matches / len(normalized)

    if ratio >= float(threshold):
        return CheckResult("stability", True, f"stability ratio {ratio:.2f} >= {threshold:.2f}", {"ratio": ratio, "threshold": threshold})

    return CheckResult("stability", False, f"stability ratio {ratio:.2f} < {threshold:.2f}", {"ratio": ratio, "threshold": threshold})


def _tokenize(text: str) -> set[str]:
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "as",
        "with",
        "by",
        "it",
        "that",
        "this",
    }
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return {w for w in words if w not in stopwords and len(w) > 1}


def _extract_claims(response: LLMResponse, params: dict[str, Any]) -> list[str]:
    explicit_claims = params.get("claims")
    if isinstance(explicit_claims, list) and all(isinstance(x, str) for x in explicit_claims):
        return [c.strip() for c in explicit_claims if c.strip()]

    claims_json_path = params.get("claims_json_path")
    if isinstance(claims_json_path, str) and claims_json_path.strip():
        try:
            payload = _ensure_json_payload(response)
            value = json_path_get(payload, claims_json_path)
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]
        except (CheckRuntimeError, KeyError):
            pass

    raw = response.text.strip()
    parts = re.split(r"(?<=[.!?])\s+|\n+", raw)
    return [p.strip() for p in parts if p.strip()]


def _extract_citations(claim: str) -> list[int]:
    cited: list[int] = []
    for match in re.finditer(r"\[(\d+)\]|\(cite\s*:\s*(\d+)\)", claim):
        value = match.group(1) or match.group(2)
        if value is None:
            continue
        try:
            cited.append(int(value))
        except ValueError:
            continue
    return cited


def _has_negation(text: str) -> bool:
    return bool(re.search(r"\b(no|not|never|cannot|can't|none|without|false)\b", text.lower()))


def check_grounding_assertion(response: LLMResponse, params: dict[str, Any], context_chunks: list[dict[str, Any]]) -> CheckResult:
    require_citations = bool(params.get("require_citations", False))
    unsupported_max = int(params.get("unsupported_claims_max", 0))
    contradicted_max = int(params.get("contradicted_claims_max", 0))
    grounding_score_min = float(params.get("grounding_score_min", 1.0))
    support_overlap = float(params.get("support_overlap_min", 0.45))
    contradiction_overlap = float(params.get("contradiction_overlap_min", 0.35))

    if not context_chunks:
        return CheckResult("grounding_assertion", False, "no context chunks supplied for grounding check")

    claims = _extract_claims(response, params)
    if not claims:
        return CheckResult("grounding_assertion", False, "no claims extracted for grounding check")

    classified: list[dict[str, Any]] = []
    supported = 0
    contradicted = 0
    insufficient = 0

    for claim in claims:
        citations = _extract_citations(claim)
        candidate_chunks = context_chunks

        if citations:
            selected: list[dict[str, Any]] = []
            for ref in citations:
                idx = ref - 1
                if 0 <= idx < len(context_chunks):
                    selected.append(context_chunks[idx])
            candidate_chunks = selected

        if require_citations and not citations:
            insufficient += 1
            classified.append(
                {
                    "claim": claim,
                    "classification": "insufficient_evidence",
                    "reason": "citation required but missing",
                    "matched_context_id": None,
                }
            )
            continue

        if not candidate_chunks:
            insufficient += 1
            classified.append(
                {
                    "claim": claim,
                    "classification": "insufficient_evidence",
                    "reason": "citation does not map to any provided context span",
                    "matched_context_id": None,
                }
            )
            continue

        claim_tokens = _tokenize(claim)
        best_chunk: dict[str, Any] | None = None
        best_score = 0.0
        for chunk in candidate_chunks:
            text = str(chunk.get("text", ""))
            chunk_tokens = _tokenize(text)
            if not claim_tokens:
                score = 0.0
            else:
                score = len(claim_tokens & chunk_tokens) / max(len(claim_tokens), 1)
            if score > best_score:
                best_score = score
                best_chunk = chunk

        if best_chunk is None or best_score < support_overlap:
            insufficient += 1
            classified.append(
                {
                    "claim": claim,
                    "classification": "insufficient_evidence",
                    "reason": f"insufficient token overlap ({best_score:.2f})",
                    "matched_context_id": best_chunk.get("id") if best_chunk else None,
                }
            )
            continue

        claim_neg = _has_negation(claim)
        chunk_neg = _has_negation(str(best_chunk.get("text", "")))
        if claim_neg != chunk_neg and best_score >= contradiction_overlap:
            contradicted += 1
            classified.append(
                {
                    "claim": claim,
                    "classification": "contradicted",
                    "reason": "negation polarity conflicts with best-matched context",
                    "matched_context_id": best_chunk.get("id"),
                    "overlap": round(best_score, 3),
                }
            )
            continue

        supported += 1
        classified.append(
            {
                "claim": claim,
                "classification": "supported",
                "reason": f"supported by context overlap {best_score:.2f}",
                "matched_context_id": best_chunk.get("id"),
                "overlap": round(best_score, 3),
            }
        )

    total = len(claims)
    score = supported / max(total, 1)
    passed = insufficient <= unsupported_max and contradicted <= contradicted_max and score >= grounding_score_min

    summary = {
        "total_claims": total,
        "supported": supported,
        "contradicted": contradicted,
        "insufficient_evidence": insufficient,
        "grounding_score": round(score, 4),
    }
    msg = (
        f"grounding score={score:.2f} supported={supported} contradicted={contradicted} "
        f"insufficient={insufficient}"
    )

    return CheckResult("grounding_assertion", passed, msg, {"summary": summary, "claims": classified})


def _first_index(events: list[dict[str, Any]], tool: str) -> int | None:
    for event in events:
        if event["tool"] == tool:
            return int(event["index"])
    return None


def _event_indices(events: list[dict[str, Any]], tool: str) -> list[int]:
    return [int(e["index"]) for e in events if e["tool"] == tool]


def check_tool_contract(trace_events: list[dict[str, Any]], params: dict[str, Any]) -> CheckResult:
    if not trace_events:
        return CheckResult("tool_contract", False, "tool_contract needs trace events")

    violations: list[dict[str, Any]] = []

    required_tools = params.get("required_tools", [])
    forbidden_tools = params.get("forbidden_tools", [])
    ordered_sequence = params.get("ordered_sequence", [])
    required_before = params.get("required_before", [])
    required_after = params.get("required_after", [])
    argument_assertions = params.get("argument_assertions", [])
    confirmation_rule = params.get("confirmation_required_before_write_action")

    if isinstance(required_tools, list):
        for tool in required_tools:
            if not isinstance(tool, str):
                continue
            if _first_index(trace_events, tool) is None:
                violations.append({"type": "missing_required_tool", "tool": tool})

    if isinstance(forbidden_tools, list):
        for tool in forbidden_tools:
            if not isinstance(tool, str):
                continue
            idxs = _event_indices(trace_events, tool)
            if idxs:
                violations.append({"type": "forbidden_tool_used", "tool": tool, "indices": idxs})

    if isinstance(required_before, list):
        for rule in required_before:
            if not isinstance(rule, dict):
                continue
            first = rule.get("first")
            then = rule.get("then")
            if not isinstance(first, str) or not isinstance(then, str):
                continue
            first_idx = _first_index(trace_events, first)
            then_idx = _first_index(trace_events, then)
            if then_idx is not None and (first_idx is None or first_idx >= then_idx):
                violations.append(
                    {
                        "type": "required_before_violation",
                        "first": first,
                        "then": then,
                        "first_index": first_idx,
                        "then_index": then_idx,
                    }
                )

    if isinstance(required_after, list):
        for rule in required_after:
            if not isinstance(rule, dict):
                continue
            tool = rule.get("tool")
            after = rule.get("after")
            if not isinstance(tool, str) or not isinstance(after, str):
                continue
            tool_idx = _first_index(trace_events, tool)
            after_idx = _first_index(trace_events, after)
            if tool_idx is not None and (after_idx is None or tool_idx <= after_idx):
                violations.append(
                    {
                        "type": "required_after_violation",
                        "tool": tool,
                        "after": after,
                        "tool_index": tool_idx,
                        "after_index": after_idx,
                    }
                )

    if isinstance(ordered_sequence, list) and all(isinstance(t, str) for t in ordered_sequence):
        cursor = -1
        for tool in ordered_sequence:
            idxs = _event_indices(trace_events, tool)
            next_idx = None
            for idx in idxs:
                if idx > cursor:
                    next_idx = idx
                    break
            if next_idx is None:
                violations.append({"type": "ordered_sequence_violation", "sequence": ordered_sequence, "missing_or_out_of_order": tool})
                break
            cursor = next_idx

    if isinstance(argument_assertions, list):
        for rule in argument_assertions:
            if not isinstance(rule, dict):
                continue
            tool = rule.get("tool")
            path = rule.get("path")
            if not isinstance(tool, str) or not isinstance(path, str):
                continue

            matching = [e for e in trace_events if e["tool"] == tool]
            if not matching:
                violations.append({"type": "argument_assertion_no_tool_event", "tool": tool, "path": path})
                continue

            satisfied = False
            for event in matching:
                args = event.get("arguments") or {}
                try:
                    value = json_path_get(args, path)
                except KeyError:
                    value = None

                if rule.get("exists") is True and value is not None:
                    satisfied = True
                    break
                if "equals" in rule and value == rule.get("equals"):
                    satisfied = True
                    break
                if isinstance(rule.get("in"), list) and value in rule.get("in"):
                    satisfied = True
                    break
                if isinstance(rule.get("contains"), str) and isinstance(value, str) and rule.get("contains") in value:
                    satisfied = True
                    break
                if isinstance(rule.get("regex"), str) and isinstance(value, str) and re.search(rule.get("regex"), value):
                    satisfied = True
                    break

            if not satisfied:
                violations.append(
                    {
                        "type": "argument_assertion_violation",
                        "tool": tool,
                        "path": path,
                        "rule": rule,
                    }
                )

    if isinstance(confirmation_rule, dict):
        confirm_tool = confirmation_rule.get("confirm_tool")
        write_tools = confirmation_rule.get("write_tools", [])
        if isinstance(confirm_tool, str) and isinstance(write_tools, list):
            confirm_idx = _first_index(trace_events, confirm_tool)
            for write_tool in write_tools:
                if not isinstance(write_tool, str):
                    continue
                for write_idx in _event_indices(trace_events, write_tool):
                    if confirm_idx is None or confirm_idx >= write_idx:
                        violations.append(
                            {
                                "type": "confirmation_required_before_write_action",
                                "confirm_tool": confirm_tool,
                                "write_tool": write_tool,
                                "confirm_index": confirm_idx,
                                "write_index": write_idx,
                            }
                        )

    passed = not violations
    message = "tool contract passed" if passed else f"tool contract violations: {len(violations)}"
    return CheckResult(
        "tool_contract",
        passed,
        message,
        {
            "violation_count": len(violations),
            "violations": violations,
            "event_count": len(trace_events),
        },
    )


def run_assertion(
    assertion: AssertionSpec,
    first_response: LLMResponse,
    responses: list[LLMResponse],
    suite: str,
    case_id: str,
    baseline_root: Path,
    update_baseline: bool,
    context_chunks: list[dict[str, Any]] | None = None,
    trace_events: list[dict[str, Any]] | None = None,
) -> CheckResult:
    kind = assertion.type
    params = assertion.params

    if kind == "schema_valid":
        return check_schema_valid(first_response, params)
    if kind == "required_fields":
        return check_required_fields(first_response, params)
    if kind == "forbidden_fields":
        return check_forbidden_fields(first_response, params)
    if kind == "regex_must_match":
        return check_regex_must_match(first_response, params)
    if kind == "regex_must_not_match":
        return check_regex_must_not_match(first_response, params)
    if kind == "json_path_equals":
        return check_json_path_equals(first_response, params)
    if kind == "json_path_in":
        return check_json_path_in(first_response, params)
    if kind == "baseline_diff":
        return check_baseline_diff(first_response, suite, case_id, baseline_root, update_baseline)
    if kind == "stability":
        return check_stability(responses, params)
    if kind == "grounding_assertion":
        return check_grounding_assertion(first_response, params, context_chunks or [])
    if kind == "tool_contract":
        return check_tool_contract(trace_events or [], params)

    return CheckResult(kind, False, f"unsupported assertion type: {kind}")
