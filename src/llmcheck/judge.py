from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from .storage.models import AppConfig, JudgeResult, SuiteTestCase


class JudgeError(Exception):
    pass


def build_judge_prompt(test: SuiteTestCase, output_text: str) -> str:
    context_text = "\n".join(f"- {item.get('id', 'context')}: {item.get('text', '')}" for item in test.context)
    return (
        "You are LLMCheck Judge.\n\n"
        "Your job is to inspect a model output against a human-approved regression check.\n"
        "You do not decide pass or fail.\n"
        "You only extract evidence of violations.\n\n"
        "Use only the approved context and expected criteria.\n"
        "Do not use outside knowledge.\n"
        "Do not reward tone or fluency.\n"
        "Do not infer missing facts.\n\n"
        "Return only valid JSON.\n\n"
        f"Inputs: {json.dumps(test.inputs, ensure_ascii=True)}\n"
        f"Approved context:\n{context_text}\n"
        f"Output:\n{output_text}\n"
        f"Must include: {json.dumps(test.expected.get('must_include', []), ensure_ascii=True)}\n"
        f"Must not claim: {json.dumps(test.expected.get('must_not_claim', []), ensure_ascii=True)}\n"
        f"Rubric: {test.judge.get('pass_if', '')}\n\n"
        "JSON schema:\n"
        "{\n"
        '  "missing_requirements": ["..."],\n'
        '  "forbidden_claims_found": ["..."],\n'
        '  "unsupported_claims": ["..."],\n'
        '  "reason": "...",\n'
        '  "confidence": "high" | "medium" | "low"\n'
        "}\n"
    )


def parse_judge_response(payload_text: str) -> JudgeResult:
    if not isinstance(payload_text, str):
        raise JudgeError("judge response must be JSON text")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise JudgeError(f"judge returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise JudgeError("judge response must be a JSON object")

    def require_string_list(key: str) -> list[str]:
        value = payload.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise JudgeError(f"judge response missing valid `{key}` string list")
        return value

    reason = payload.get("reason")
    confidence = payload.get("confidence")
    if not isinstance(reason, str):
        raise JudgeError("judge response missing valid `reason`")
    if not isinstance(confidence, str) or confidence not in {"high", "medium", "low"}:
        raise JudgeError("judge response missing valid `confidence`")

    return JudgeResult(
        missing_requirements=require_string_list("missing_requirements"),
        forbidden_claims_found=require_string_list("forbidden_claims_found"),
        unsupported_claims=require_string_list("unsupported_claims"),
        reason=reason,
        confidence=confidence,
    )


def _call_openai_judge(config: AppConfig, prompt: str) -> str:
    if config.judge.provider != "openai":
        raise JudgeError(f"unsupported judge provider for V1: {config.judge.provider}")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise JudgeError("missing OPENAI_API_KEY for judge evaluation")

    payload = {
        "model": config.judge.model,
        "temperature": 0,
        "max_completion_tokens": 512,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        url="https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise JudgeError(f"judge HTTP error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise JudgeError(f"judge network error: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise JudgeError(f"judge network error: {exc}") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise JudgeError("judge returned an invalid response body") from exc

    if not isinstance(data, dict):
        raise JudgeError("judge response envelope must be an object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise JudgeError("judge response missing valid choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise JudgeError("judge response missing valid message")
    content = message.get("content", "")
    if isinstance(content, list):
        content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    if not isinstance(content, str):
        raise JudgeError("judge returned non-text content")
    return content


def evaluate_output(
    config: AppConfig,
    test: SuiteTestCase,
    output_text: str,
    *,
    transport: Callable[[AppConfig, str], str] | None = None,
) -> JudgeResult:
    prompt = build_judge_prompt(test, output_text)
    payload_text = (transport or _call_openai_judge)(config, prompt)
    return parse_judge_response(payload_text)
