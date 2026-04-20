from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import AppConfig, CaseSpec, LLMResponse


class ProviderError(Exception):
    pass


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[dict[str, Any], int]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=body, method="POST")
    for key, value in headers.items():
        req.add_header(key, value)
    req.add_header("Content-Type", "application/json")

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            latency_ms = int((time.perf_counter() - start) * 1000)
            return json.loads(raw), latency_ms
    except urllib.error.HTTPError as exc:
        payload_text = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {exc.code}: {payload_text}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Network error: {exc.reason}") from exc


def _resolve_api_key(config: AppConfig, provider: str) -> str:
    if provider not in config.providers:
        raise ProviderError(f"Provider `{provider}` not configured")
    env = config.providers[provider].api_key_env
    key = os.getenv(env)
    if not key:
        raise ProviderError(f"Missing API key env var for provider `{provider}`: {env}")
    return key


def _append_context(messages: list[dict[str, str]], context: list[str]) -> list[dict[str, str]]:
    if not context:
        return messages
    ctx = "\n\n".join(context)
    ctx_msg = {"role": "system", "content": f"Additional context:\n{ctx}"}
    return [ctx_msg, *messages]


def _policy_instruction(case: CaseSpec) -> str:
    parts = [f"Use {case.policy.reasoning_level} reasoning for this task."]
    if case.policy.allow_planning:
        parts.append("Do internal planning and context gathering before answering.")
    if case.policy.sparring_mode:
        parts.append("Act as an intellectual sparring partner, not an agreeable assistant.")
    if case.policy.conversational_style:
        parts.append("Write in a conversational tone.")
    if case.policy.unpredictable_style:
        parts.append("Vary sentence structure and avoid repetitive phrasing.")
    return " ".join(parts)


def _append_policy(messages: list[dict[str, str]], case: CaseSpec) -> list[dict[str, str]]:
    instruction = _policy_instruction(case)
    policy_msg = {"role": "system", "content": instruction}
    return [policy_msg, *messages]


def _load_case_context(case: CaseSpec) -> list[str]:
    contents: list[str] = []
    for path in case.context_files:
        try:
            contents.append(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ProviderError(f"Context file not found: {path}")
    return contents


def call_openai(config: AppConfig, case: CaseSpec) -> LLMResponse:
    key = _resolve_api_key(config, "openai")
    provider_cfg = config.providers["openai"]
    base_url = provider_cfg.base_url or "https://api.openai.com/v1"

    context = _load_case_context(case)
    messages = _append_context(case.messages, context)
    messages = _append_policy(messages, case)

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": case.model,
        "messages": messages,
        "temperature": 0,
    }
    data, latency_ms = _http_json(
        url,
        payload,
        {
            "Authorization": f"Bearer {key}",
        },
    )

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content")
    if isinstance(text, list):
        text = "\n".join(str(chunk.get("text", "")) for chunk in text if isinstance(chunk, dict))
    if not isinstance(text, str):
        text = ""

    return LLMResponse(
        text=text,
        structured=None,
        metadata={
            "latency_ms": latency_ms,
            "provider": "openai",
            "usage": data.get("usage") or {},
        },
    )


def call_anthropic(config: AppConfig, case: CaseSpec) -> LLMResponse:
    key = _resolve_api_key(config, "anthropic")
    provider_cfg = config.providers["anthropic"]
    base_url = provider_cfg.base_url or "https://api.anthropic.com/v1"

    context = _load_case_context(case)
    messages = _append_context(case.messages, context)
    messages = _append_policy(messages, case)

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    chat_messages = [m for m in messages if m["role"] != "system"]

    payload: dict[str, Any] = {
        "model": case.model,
        "max_tokens": 2048,
        "messages": chat_messages,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    url = f"{base_url.rstrip('/')}/messages"
    data, latency_ms = _http_json(
        url,
        payload,
        {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )

    text_parts: list[str] = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))

    return LLMResponse(
        text="\n".join(text_parts),
        structured=None,
        metadata={
            "latency_ms": latency_ms,
            "provider": "anthropic",
            "usage": data.get("usage") or {},
        },
    )


def call_gemini(config: AppConfig, case: CaseSpec) -> LLMResponse:
    key = _resolve_api_key(config, "gemini")
    provider_cfg = config.providers["gemini"]
    base_url = provider_cfg.base_url or "https://generativelanguage.googleapis.com/v1beta"

    context = _load_case_context(case)
    messages = _append_context(case.messages, context)
    messages = _append_policy(messages, case)

    parts = [{"text": m["content"]} for m in messages]
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {"temperature": 0},
    }

    model_escaped = urllib.parse.quote(case.model, safe="")
    url = f"{base_url.rstrip('/')}/models/{model_escaped}:generateContent?key={urllib.parse.quote(key, safe='')}"

    data, latency_ms = _http_json(url, payload, {})

    text_parts: list[str] = []
    candidates = data.get("candidates") or []
    if candidates:
        first = candidates[0]
        content = first.get("content") if isinstance(first, dict) else None
        for part in (content or {}).get("parts", []):
            if isinstance(part, dict) and "text" in part:
                text_parts.append(str(part["text"]))

    return LLMResponse(
        text="\n".join(text_parts),
        structured=None,
        metadata={
            "latency_ms": latency_ms,
            "provider": "gemini",
            "usage": data.get("usageMetadata") or {},
        },
    )


def call_provider(config: AppConfig, case: CaseSpec) -> LLMResponse:
    provider = case.provider.lower()
    if provider == "openai":
        return call_openai(config, case)
    if provider == "anthropic":
        return call_anthropic(config, case)
    if provider == "gemini":
        return call_gemini(config, case)
    raise ProviderError(f"Unsupported provider: {case.provider}")
