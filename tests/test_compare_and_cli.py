from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llmcheck.compare import execute_compare
from llmcheck.models import AppConfig, AssertionSpec, CaseSpec, PromptPolicy, ProviderConfig, SuiteSpec, VariantSpec, LLMResponse


class CompareAndCliTests(unittest.TestCase):
    def test_compare_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = AppConfig(
                root_dir=root,
                providers={
                    "openai": ProviderConfig(api_key_env="OPENAI_API_KEY"),
                    "anthropic": ProviderConfig(api_key_env="ANTHROPIC_API_KEY"),
                },
                suites=[SuiteSpec(name="s", case_globs=[])],
            )

            case = CaseSpec(
                id="case1",
                suite="s",
                provider="openai",
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": "hi"}],
                assertions=[
                    AssertionSpec(type="schema_valid", params={"schema": {"type": "object", "required": ["result"], "properties": {"result": {"type": "string"}}}}),
                    AssertionSpec(type="grounding_assertion", params={"claims_json_path": "claims", "unsupported_claims_max": 0, "contradicted_claims_max": 0, "grounding_score_min": 0.5}),
                    AssertionSpec(type="tool_contract", params={"required_tools": ["retrieve_policy"]}),
                ],
                path=root / "dummy.yaml",
                context_chunks=[{"id": "c1", "text": "policy says refunds need review"}],
                trace_events=[{"tool": "retrieve_policy", "arguments": {"id": "refund"}}],
                policy=PromptPolicy(),
            )

            def fake_call_provider(_config, variant_case):
                text = json.dumps({"result": "ok", "claims": ["refunds need review"]})
                return LLMResponse(text=text, structured=None, metadata={"latency_ms": 12, "usage": {"total_tokens": 25}})

            with patch("llmcheck.compare.call_provider", side_effect=fake_call_provider):
                report = execute_compare(
                    config=config,
                    cases=[case],
                    variants=[
                        VariantSpec(name="v1", provider="openai", model="gpt-4.1-mini"),
                        VariantSpec(name="v2", provider="anthropic", model="claude-3-5-sonnet-latest"),
                    ],
                    repeats_override=1,
                    baseline_root=root / ".llmcheck" / "baselines",
                    report_path=root / ".llmcheck" / "reports" / "compare-latest.json",
                )

            self.assertEqual(len(report["matrix"]), 2)
            self.assertTrue(all(row["passed"] for row in report["matrix"]))

    def test_cli_init_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

            cmd = [sys.executable, "-m", "llmcheck.cli", "init", "--dir", str(cwd)]
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue((cwd / "llmcheck.yaml").exists())


if __name__ == "__main__":
    unittest.main()
