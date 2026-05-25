from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .storage.models import AppConfig, JudgeConfig, StorageConfig, SuiteRunnerConfig, SuiteSpec, SuiteTestCase


class ConfigError(Exception):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"top-level YAML must be a map: {path}")
    return data


def load_config(config_path: Path) -> AppConfig:
    raw = _load_yaml(config_path)
    root_dir = config_path.parent.resolve()

    storage_raw = raw.get("storage") or {}
    if not isinstance(storage_raw, dict):
        raise ConfigError("`storage` must be a map")
    storage_path = storage_raw.get("path", ".llmcheck/llmcheck.db")
    if not isinstance(storage_path, str) or not storage_path.strip():
        raise ConfigError("storage.path must be a non-empty string")

    judge_raw = raw.get("judge") or {}
    if not isinstance(judge_raw, dict):
        raise ConfigError("`judge` must be a map")
    provider = judge_raw.get("provider", "openai")
    model = judge_raw.get("model", "gpt-4o-mini")
    if not isinstance(provider, str) or not provider.strip():
        raise ConfigError("judge.provider must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError("judge.model must be a non-empty string")

    return AppConfig(
        root_dir=root_dir,
        storage=StorageConfig(path=(root_dir / storage_path).resolve()),
        judge=JudgeConfig(provider=provider, model=model),
    )


def load_suite(suite_path: Path) -> SuiteSpec:
    raw = _load_yaml(suite_path)
    runner_raw = raw.get("runner")
    tests_raw = raw.get("tests")
    if not isinstance(runner_raw, dict):
        raise ConfigError("suite `runner` must be a map")
    if not isinstance(tests_raw, list):
        raise ConfigError("suite `tests` must be a list")

    runner_type = runner_raw.get("type")
    runner_callable = runner_raw.get("callable")
    if runner_type != "python":
        raise ConfigError("runner.type must be `python` for V1")
    if not isinstance(runner_callable, str) or ":" not in runner_callable:
        raise ConfigError("runner.callable must be `module.path:function_name`")

    tests: list[SuiteTestCase] = []
    for item in tests_raw:
        if not isinstance(item, dict):
            raise ConfigError("each suite test must be a map")
        test_id = item.get("id")
        source_run_id = item.get("source_run_id")
        source_reason = item.get("source_reason")
        metadata = item.get("metadata") or {}
        inputs = item.get("inputs") or {}
        context = item.get("context") or []
        expected = item.get("expected") or {}
        judge = item.get("judge") or {}
        if not isinstance(test_id, str) or not test_id.strip():
            raise ConfigError("suite test missing `id`")
        if not isinstance(source_run_id, str) or not source_run_id.strip():
            raise ConfigError(f"suite test `{test_id}` missing `source_run_id`")
        if not isinstance(source_reason, str) or not source_reason.strip():
            raise ConfigError(f"suite test `{test_id}` missing `source_reason`")
        if not isinstance(metadata, dict):
            raise ConfigError(f"suite test `{test_id}` metadata must be a map")
        if not isinstance(inputs, dict):
            raise ConfigError(f"suite test `{test_id}` inputs must be a map")
        if not isinstance(context, list):
            raise ConfigError(f"suite test `{test_id}` context must be a list")
        if not isinstance(expected, dict):
            raise ConfigError(f"suite test `{test_id}` expected must be a map")
        if not isinstance(judge, dict):
            raise ConfigError(f"suite test `{test_id}` judge must be a map")
        must_include = expected.get("must_include") or []
        must_not_claim = expected.get("must_not_claim") or []
        if not isinstance(must_include, list) or not all(isinstance(x, str) for x in must_include):
            raise ConfigError(f"suite test `{test_id}` expected.must_include must be a string list")
        if not isinstance(must_not_claim, list) or not all(isinstance(x, str) for x in must_not_claim):
            raise ConfigError(f"suite test `{test_id}` expected.must_not_claim must be a string list")
        tests.append(
            SuiteTestCase(
                id=test_id,
                source_run_id=source_run_id,
                source_reason=source_reason,
                metadata=metadata,
                inputs=inputs,
                context=context,
                expected={"must_include": must_include, "must_not_claim": must_not_claim},
                judge=judge,
            )
        )

    return SuiteSpec(runner=SuiteRunnerConfig(type="python", callable=runner_callable), tests=tests)
