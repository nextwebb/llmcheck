from __future__ import annotations

import pytest

from llmcheck.judge import JudgeError, parse_judge_response


def test_valid_json_parses_and_ignores_extra_status() -> None:
    result = parse_judge_response(
        """
        {
          "missing_requirements": [],
          "forbidden_claims_found": [],
          "unsupported_claims": [],
          "reason": "fine",
          "confidence": "high",
          "status": "pass"
        }
        """
    )
    assert result.reason == "fine"
    assert result.confidence == "high"


def test_invalid_json_raises_clear_error() -> None:
    with pytest.raises(JudgeError, match="invalid JSON"):
        parse_judge_response("{")


def test_missing_required_arrays_raise_clear_error() -> None:
    with pytest.raises(JudgeError, match="missing valid `missing_requirements`"):
        parse_judge_response(
            """
            {
              "forbidden_claims_found": [],
              "unsupported_claims": [],
              "reason": "fine",
              "confidence": "high"
            }
            """
        )
