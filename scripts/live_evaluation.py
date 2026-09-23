"""Explicitly opted-in, at most twelve synthetic OpenAI judge requests. No retries."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from llmcheck.judge import evaluate_output, _call_openai_judge
from llmcheck.storage.models import AppConfig, StorageConfig, JudgeConfig, SuiteTestCase

FIXTURES = {'policy': 'Refunds above $100 require manager approval and take 3-5 business days. Approval is not guaranteed and no cash bonus is promised.', 'label_provenance': 'Hand-authored expectations defined before runner invocation; not live-model labels or independent adjudication.', 'cases': [{'id': 'literal_clear', 'category': 'compliant_literal', 'response': 'Refunds above $100 require manager approval and take 3-5 business days.', 'expected_policy_compliant': True, 'expected_reason': 'States both requirements; no contradictory or unsupported promise.'}, {'id': 'literal_no_guarantee', 'category': 'compliant_literal', 'response': 'Manager approval is required. Processing takes 3-5 business days; approval is not guaranteed.', 'expected_policy_compliant': True, 'expected_reason': 'States both requirements and accurately denies guaranteed approval.'}, {'id': 'paraphrase_supervisor', 'category': 'compliant_paraphrase', 'response': 'For a refund over $100, a manager must approve it, and processing takes three to five business days.', 'expected_policy_compliant': True, 'expected_reason': 'Faithful paraphrase preserves approval and processing window.'}, {'id': 'paraphrase_both', 'category': 'compliant_paraphrase', 'response': 'A refund above $100 needs approval from a manager and takes between three and five business days.', 'expected_policy_compliant': True, 'expected_reason': 'Both policy facts expressed without literal required phrases.'}, {'id': 'negated_instant', 'category': 'compliant_negation', 'response': 'Refunds above $100 require manager approval and take 3-5 business days. They are not instant.', 'expected_policy_compliant': True, 'expected_reason': 'Explicitly denies instant refund; does not promise one.'}, {'id': 'negated_claim', 'category': 'compliant_negation', 'response': 'Manager approval is required and processing takes 3-5 business days. Do not expect an instant refund.', 'expected_policy_compliant': True, 'expected_reason': 'Required facts plus denial of immediacy are compliant.'}, {'id': 'missing_approval', 'category': 'missing_fact', 'response': 'Refunds above $100 take 3-5 business days.', 'expected_policy_compliant': False, 'expected_reason': 'Omits required manager approval.'}, {'id': 'missing_timing', 'category': 'missing_fact', 'response': 'Refunds above $100 require manager approval.', 'expected_policy_compliant': False, 'expected_reason': 'Omits required processing window.'}, {'id': 'contradiction_approval', 'category': 'contradiction_with_keywords', 'response': 'Manager approval is not required for refunds above $100; processing takes 3-5 business days.', 'expected_policy_compliant': False, 'expected_reason': 'Contains approval words but expressly contradicts required approval.'}, {'id': 'contradiction_timing', 'category': 'contradiction_with_keywords', 'response': 'Refunds above $100 require manager approval, but do not take 3-5 business days; the money arrives today.', 'expected_policy_compliant': False, 'expected_reason': 'Contains timing words but contradicts processing window.'}, {'id': 'unsupported_guarantee', 'category': 'unsupported_extra', 'response': 'Refunds above $100 require manager approval and take 3-5 business days. Approval is guaranteed.', 'expected_policy_compliant': False, 'expected_reason': 'Adds an unsupported guarantee directly excluded by policy.'}, {'id': 'unsupported_bonus', 'category': 'unsupported_extra', 'response': 'Refunds above $100 require manager approval and take 3-5 business days. You also receive a guaranteed $25 cash bonus.', 'expected_policy_compliant': False, 'expected_reason': 'Adds a guaranteed cash benefit not promised by policy.'}]}

def evaluate(*, model: str, output: Path, opt_in: bool, limit: int = 12,
             transport: Callable | None = None) -> dict:
    if not opt_in:
        raise ValueError("Explicit opt-in required: --allow-live-model-calls")
    if not 1 <= limit <= 12:
        raise ValueError("limit must be between 1 and 12")
    if not model.strip():
        raise ValueError("model must not be empty")
    if transport is None and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY must be set in the environment")
    # Exclusive creation prevents overwriting earlier evidence or following a file symlink.
    with output.open("x", encoding="utf-8") as stream:
        config = AppConfig(REPO, StorageConfig(Path("unused-synthetic.db")), JudgeConfig("openai", model))
        report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "judge_source_sha256": hashlib.sha256((REPO / "src/llmcheck/judge.py").read_bytes()).hexdigest(),
            "fixture_sha256": hashlib.sha256(json.dumps(FIXTURES, sort_keys=True).encode()).hexdigest(),
            "model": model, "transport": "injected_test_double" if transport else "default_openai_judge",
            "request_limit": limit, "attempted_requests": 0, "retries": 0,
            "usage": None, "usage_note": "Existing judge transport returns content only; token usage is unavailable, not zero.",
            "positive_class": "policy compliant / judge PASS",
            "limits": ["Purposively authored synthetic cases; not representative accuracy or a production benchmark.",
                       "Labels authored before evaluation, not independently adjudicated.",
                       "No timing, price or token metrics inferred.",
                       "Exceptions are recorded by type only; provider error bodies are not logged."],
            "results": [],
        }
        def persist():
            stream.seek(0); json.dump(report, stream, indent=2); stream.write("\n"); stream.truncate(); stream.flush()
        persist()
        for case in FIXTURES["cases"][:limit]:
            test = SuiteTestCase(case["id"], "synthetic-authored", "Controlled evaluation", {},
                {"query": "Can I get a refund above $100?"},
                [{"id": "policy", "text": FIXTURES["policy"]}],
                {"must_include": ["manager approval", "3-5 business days"], "must_not_claim": ["instant"]},
                {"type": "rubric", "pass_if": "Preserve policy meaning, permit paraphrases and negation, reject contradictory or unsupported promises."})
            report["attempted_requests"] += 1
            persist()
            try:
                result = evaluate_output(config, test, case["response"], transport=transport or _call_openai_judge)
                passed = not bool(result.missing_requirements or result.forbidden_claims_found or result.unsupported_claims)
                expected = case["expected_policy_compliant"]
                classification = ("true_positive" if passed else "false_negative") if expected else ("false_positive" if passed else "true_negative")
                report["results"].append({**case, "status": "evaluated", "passed": passed,
                                          "classification": classification, "judge": asdict(result)})
            except Exception as exc:
                report["results"].append({**case, "status": "error", "error_type": type(exc).__name__})
                # Stop on the first provider/runtime failure; never spend the remaining budget blindly.
                persist()
                break
            persist()
        report["confusion_counts"] = {key: sum(r.get("classification") == key for r in report["results"])
            for key in ["true_positive", "true_negative", "false_positive", "false_negative"]}
        report["errors"] = sum(r["status"] == "error" for r in report["results"])
        report["evaluated_cases"] = sum(r["status"] == "evaluated" for r in report["results"])
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        persist()
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live-model-calls", action="store_true")
    parser.add_argument("--model", required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(model=args.model, output=args.output, opt_in=args.allow_live_model_calls, limit=args.limit)
    except (ValueError, OSError) as exc:
        # Our validation strings contain no credentials; OSError paths may be user-selected.
        parser.error(str(exc))
    print(json.dumps({"evaluated_cases": report["evaluated_cases"], "errors": report["errors"],
                      "attempted_requests": report["attempted_requests"], "confusion_counts": report["confusion_counts"]}))
    return 2 if report["errors"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
