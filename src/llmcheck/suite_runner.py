from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .config import load_suite
from .judge import JudgeError, evaluate_output
from .storage.models import AppConfig, SuiteRunResult, SuiteTestResult


class SuiteRunError(Exception):
    pass


@contextmanager
def _prepend_import_path(path: Path):
    raw = str(path.resolve())
    inserted = False
    if raw not in sys.path:
        sys.path.insert(0, raw)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(raw)
            except ValueError:
                pass


def import_callable(path: str, *, working_dir: Path | None = None) -> Callable[..., Any]:
    if ":" not in path:
        raise SuiteRunError("callable path must be `module.path:function_name`")
    module_name, func_name = path.split(":", 1)
    try:
        with _prepend_import_path(working_dir or Path.cwd()):
            module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SuiteRunError(f"could not import module `{module_name}`") from exc
    try:
        func = getattr(module, func_name)
    except AttributeError as exc:
        raise SuiteRunError(f"callable `{func_name}` not found in `{module_name}`") from exc
    if not callable(func):
        raise SuiteRunError(f"`{path}` is not callable")
    return func


def _coerce_output_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if hasattr(result, "choices"):
        choices = getattr(result, "choices", None)
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            content = getattr(message, "content", "") if message is not None else ""
            return str(content or "")
    return str(result)


def run_suite(config: AppConfig, suite_path, *, judge_transport=None) -> SuiteRunResult:
    suite = load_suite(suite_path)
    suite_path = Path(suite_path)
    runner = import_callable(suite.runner.callable, working_dir=suite_path.parent)
    results: list[SuiteTestResult] = []

    for test in suite.tests:
        try:
            output = runner(**test.inputs)
        except Exception as exc:  # noqa: BLE001
            raise SuiteRunError(f"runner callable failed for `{test.id}`: {exc}") from exc
        output_text = _coerce_output_text(output)
        try:
            judge_result = evaluate_output(config, test, output_text, transport=judge_transport)
        except JudgeError as exc:
            raise SuiteRunError(str(exc)) from exc
        violations = (
            judge_result.missing_requirements
            or judge_result.forbidden_claims_found
            or judge_result.unsupported_claims
        )
        results.append(
            SuiteTestResult(
                test_id=test.id,
                passed=not bool(violations),
                judge_result=judge_result,
            )
        )

    return SuiteRunResult(
        passed=all(item.passed for item in results),
        results=results,
    )
