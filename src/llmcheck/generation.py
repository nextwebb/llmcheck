from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError, load_suite
from .storage.models import RunRecord, SuiteSpec


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "regression_case"


def _extract_inputs(run: RunRecord) -> dict[str, Any]:
    user_input = run.input_json.get("user_input")
    if isinstance(user_input, str) and user_input.strip():
        return {"query": user_input}
    return {"query": ""}


def _extract_must_not_claim(correction_text: str) -> list[str]:
    matches = re.findall(r'"([^"]+)"', correction_text)
    return [m.strip() for m in matches if m.strip()]


def draft_regression_case(run: RunRecord, correction_text: str) -> dict[str, Any]:
    query = str(_extract_inputs(run).get("query", "")).strip()
    id_seed = query or run.id
    must_not_claim = _extract_must_not_claim(correction_text)
    must_include = [correction_text.strip()] if correction_text.strip() else []
    pass_if = correction_text.strip() or "The answer should satisfy the approved correction."

    return {
        "id": _slugify(id_seed)[:48],
        "source_run_id": run.id,
        "source_reason": run.flag_reason or correction_text.strip() or "reviewed locally",
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_by": "local",
        },
        "inputs": _extract_inputs(run),
        "context": run.context,
        "expected": {
            "must_include": must_include,
            "must_not_claim": must_not_claim,
        },
        "judge": {
            "type": "rubric",
            "pass_if": pass_if,
        },
    }


def dump_regression_case(case: dict[str, Any]) -> str:
    return yaml.safe_dump(case, sort_keys=False, allow_unicode=False)


def validate_regression_case_yaml(yaml_text: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML draft: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("generated regression case must be a YAML map")
    required = ["id", "source_run_id", "source_reason", "metadata", "inputs", "context", "expected", "judge"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ConfigError(f"generated regression case missing fields: {', '.join(missing)}")
    return payload


def initialize_suite_file(path: Path, *, runner_callable: str = "examples.rag_support_agent:answer_user", force: bool = False) -> None:
    if path.exists() and not force:
        return
    content = {
        "runner": {"type": "python", "callable": runner_callable},
        "tests": [],
    }
    path.write_text(yaml.safe_dump(content, sort_keys=False, allow_unicode=False), encoding="utf-8")


def append_case_to_suite(path: Path, case: dict[str, Any]) -> None:
    if not path.exists():
        initialize_suite_file(path)
    suite = load_suite(path)
    tests = [
        {
            "id": item.id,
            "source_run_id": item.source_run_id,
            "source_reason": item.source_reason,
            "metadata": item.metadata,
            "inputs": item.inputs,
            "context": item.context,
            "expected": item.expected,
            "judge": item.judge,
        }
        for item in suite.tests
    ]
    tests.append(case)
    payload = {
        "runner": {
            "type": suite.runner.type,
            "callable": suite.runner.callable,
        },
        "tests": tests,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
