from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import AppConfig, AssertionSpec, CaseSpec, PromptPolicy, ProviderConfig, SuiteSpec, VariantSpec


class ConfigError(Exception):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Top-level config must be a map: {path}")
    return data


def load_config(config_path: Path) -> AppConfig:
    raw = _load_yaml(config_path)
    root_dir = config_path.parent.resolve()

    raw_providers = raw.get("providers", {})
    if not isinstance(raw_providers, dict):
        raise ConfigError("`providers` must be a map")

    providers: dict[str, ProviderConfig] = {}
    for name, p in raw_providers.items():
        if not isinstance(p, dict):
            raise ConfigError(f"provider `{name}` must be a map")
        api_key_env = p.get("api_key_env")
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise ConfigError(f"provider `{name}` missing `api_key_env`")
        base_url = p.get("base_url")
        if base_url is not None and not isinstance(base_url, str):
            raise ConfigError(f"provider `{name}` has invalid `base_url`")
        providers[name] = ProviderConfig(api_key_env=api_key_env, base_url=base_url)

    raw_suites = raw.get("suites", [])
    if not isinstance(raw_suites, list) or not raw_suites:
        raise ConfigError("`suites` must be a non-empty list")

    suites: list[SuiteSpec] = []
    for item in raw_suites:
        if not isinstance(item, dict):
            raise ConfigError("each suite must be a map")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("suite missing `name`")
        case_globs = item.get("cases", [])
        if isinstance(case_globs, str):
            case_globs = [case_globs]
        if not isinstance(case_globs, list) or not case_globs:
            raise ConfigError(f"suite `{name}` needs non-empty `cases`")
        if not all(isinstance(g, str) and g.strip() for g in case_globs):
            raise ConfigError(f"suite `{name}` has invalid case globs")
        suites.append(SuiteSpec(name=name, case_globs=case_globs))

    raw_variants = raw.get("variants", [])
    variants: list[VariantSpec] = []
    if raw_variants is not None:
        if not isinstance(raw_variants, list):
            raise ConfigError("`variants` must be a list")
        for item in raw_variants:
            if not isinstance(item, dict):
                raise ConfigError("each variant must be a map")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ConfigError("variant missing `name`")
            provider = item.get("provider")
            model = item.get("model")
            prompt_prefix = item.get("prompt_prefix")
            if provider is not None and not isinstance(provider, str):
                raise ConfigError(f"variant `{name}` has invalid `provider`")
            if model is not None and not isinstance(model, str):
                raise ConfigError(f"variant `{name}` has invalid `model`")
            if prompt_prefix is not None and not isinstance(prompt_prefix, str):
                raise ConfigError(f"variant `{name}` has invalid `prompt_prefix`")
            variants.append(VariantSpec(name=name, provider=provider, model=model, prompt_prefix=prompt_prefix))

    return AppConfig(root_dir=root_dir, providers=providers, suites=suites, variants=variants)


def _read_case(path: Path, suite: str) -> CaseSpec:
    raw = _load_yaml(path)

    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        case_id = path.stem

    provider = raw.get("provider")
    model = raw.get("model")
    if not isinstance(provider, str) or not provider.strip():
        raise ConfigError(f"{path}: missing provider")
    if not isinstance(model, str) or not model.strip():
        raise ConfigError(f"{path}: missing model")

    messages = raw.get("messages")
    prompt = raw.get("prompt")
    if messages is None and isinstance(prompt, str) and prompt.strip():
        messages = [{"role": "user", "content": prompt}]

    if not isinstance(messages, list) or not messages:
        raise ConfigError(f"{path}: `messages` must be a non-empty list")

    normalized_messages: list[dict[str, str]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            raise ConfigError(f"{path}: each message must be a map")
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ConfigError(f"{path}: invalid message role/content")
        normalized_messages.append({"role": role, "content": content})

    raw_context_files = raw.get("context_files", [])
    if raw_context_files is None:
        raw_context_files = []
    if not isinstance(raw_context_files, list):
        raise ConfigError(f"{path}: `context_files` must be a list")
    context_files: list[Path] = []
    for item in raw_context_files:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{path}: invalid context_files item")
        context_files.append((path.parent / item).resolve())

    raw_context_chunks = raw.get("context_chunks", [])
    if raw_context_chunks is None:
        raw_context_chunks = []
    if not isinstance(raw_context_chunks, list):
        raise ConfigError(f"{path}: `context_chunks` must be a list")
    context_chunks: list[dict[str, Any]] = []
    for chunk in raw_context_chunks:
        if isinstance(chunk, str):
            context_chunks.append({"id": f"chunk-{len(context_chunks) + 1}", "text": chunk})
            continue
        if isinstance(chunk, dict):
            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ConfigError(f"{path}: each context chunk map needs non-empty `text`")
            chunk_id = chunk.get("id")
            if chunk_id is not None and not isinstance(chunk_id, str):
                raise ConfigError(f"{path}: context chunk `id` must be a string")
            context_chunks.append({"id": chunk_id or f"chunk-{len(context_chunks) + 1}", "text": text})
            continue
        raise ConfigError(f"{path}: invalid context chunk entry")

    trace_file_raw = raw.get("trace_file")
    trace_file: Path | None = None
    if trace_file_raw is not None:
        if not isinstance(trace_file_raw, str) or not trace_file_raw.strip():
            raise ConfigError(f"{path}: `trace_file` must be a non-empty string path")
        trace_file = (path.parent / trace_file_raw).resolve()

    raw_trace_events = raw.get("trace_events", [])
    if raw_trace_events is None:
        raw_trace_events = []
    if not isinstance(raw_trace_events, list):
        raise ConfigError(f"{path}: `trace_events` must be a list")
    trace_events: list[dict[str, Any]] = []
    for event in raw_trace_events:
        if not isinstance(event, dict):
            raise ConfigError(f"{path}: each trace event must be a map")
        trace_events.append(event)

    raw_assertions = raw.get("assertions", [])
    if not isinstance(raw_assertions, list) or not raw_assertions:
        raise ConfigError(f"{path}: `assertions` must be a non-empty list")

    assertions: list[AssertionSpec] = []
    for assertion in raw_assertions:
        if not isinstance(assertion, dict):
            raise ConfigError(f"{path}: each assertion must be a map")
        check_type = assertion.get("type")
        if not isinstance(check_type, str) or not check_type.strip():
            raise ConfigError(f"{path}: assertion missing `type`")
        params = {k: v for k, v in assertion.items() if k != "type"}
        assertions.append(AssertionSpec(type=check_type, params=params))

    baseline_enabled = bool(raw.get("baseline", {}).get("enabled", True)) if isinstance(raw.get("baseline"), dict) else True
    repeats = raw.get("repeats", 1)
    if not isinstance(repeats, int) or repeats < 1:
        raise ConfigError(f"{path}: repeats must be an integer >= 1")

    policy_raw = raw.get("policy", {})
    if policy_raw is None:
        policy_raw = {}
    if not isinstance(policy_raw, dict):
        raise ConfigError(f"{path}: policy must be a map")

    reasoning_level = policy_raw.get("reasoning_level", "medium")
    if reasoning_level not in {"low", "medium", "high"}:
        raise ConfigError(f"{path}: policy.reasoning_level must be low|medium|high")

    allow_planning = policy_raw.get("allow_planning", True)
    sparring_mode = policy_raw.get("sparring_mode", True)
    conversational_style = policy_raw.get("conversational_style", False)
    unpredictable_style = policy_raw.get("unpredictable_style", False)
    if not isinstance(allow_planning, bool):
        raise ConfigError(f"{path}: policy.allow_planning must be boolean")
    if not isinstance(sparring_mode, bool):
        raise ConfigError(f"{path}: policy.sparring_mode must be boolean")
    if not isinstance(conversational_style, bool):
        raise ConfigError(f"{path}: policy.conversational_style must be boolean")
    if not isinstance(unpredictable_style, bool):
        raise ConfigError(f"{path}: policy.unpredictable_style must be boolean")

    return CaseSpec(
        id=case_id,
        suite=suite,
        provider=provider,
        model=model,
        messages=normalized_messages,
        assertions=assertions,
        path=path,
        context_files=context_files,
        context_chunks=context_chunks,
        trace_file=trace_file,
        trace_events=trace_events,
        baseline_enabled=baseline_enabled,
        repeats=repeats,
        policy=PromptPolicy(
            reasoning_level=reasoning_level,
            allow_planning=allow_planning,
            sparring_mode=sparring_mode,
            conversational_style=conversational_style,
            unpredictable_style=unpredictable_style,
        ),
    )


def load_cases(config: AppConfig, suite_filter: str | None = None) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    for suite in config.suites:
        if suite_filter and suite.name != suite_filter:
            continue
        for pattern in suite.case_globs:
            for path in sorted(config.root_dir.glob(pattern)):
                if path.is_file():
                    cases.append(_read_case(path.resolve(), suite.name))

    if not cases:
        detail = f" for suite `{suite_filter}`" if suite_filter else ""
        raise ConfigError(f"No cases found{detail}")

    seen: set[tuple[str, str]] = set()
    for case in cases:
        key = (case.suite, case.id)
        if key in seen:
            raise ConfigError(f"Duplicate case id in suite `{case.suite}`: {case.id}")
        seen.add(key)

    return cases
