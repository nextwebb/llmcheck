from __future__ import annotations

import unittest

from llmcheck.checks import check_grounding_assertion
from llmcheck.models import LLMResponse


class GroundingAssertionTests(unittest.TestCase):
    def test_supported_claim(self) -> None:
        response = LLMResponse(text="Refunds under $100 can be auto-approved.", structured=None, metadata={})
        context = [{"id": "c1", "text": "Refunds under $100 can be auto-approved by the system."}]
        result = check_grounding_assertion(
            response,
            {
                "unsupported_claims_max": 0,
                "contradicted_claims_max": 0,
                "grounding_score_min": 1.0,
            },
            context,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.details["summary"]["supported"], 1)

    def test_contradicted_claim(self) -> None:
        response = LLMResponse(text="Refunds are not auto-approved.", structured=None, metadata={})
        context = [{"id": "c1", "text": "Refunds are auto-approved for low-risk orders."}]
        result = check_grounding_assertion(
            response,
            {
                "unsupported_claims_max": 0,
                "contradicted_claims_max": 0,
                "grounding_score_min": 0.0,
                "support_overlap_min": 0.2,
                "contradiction_overlap_min": 0.2,
            },
            context,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.details["summary"]["contradicted"], 1)

    def test_insufficient_evidence(self) -> None:
        response = LLMResponse(text="The policy requires biometric verification.", structured=None, metadata={})
        context = [{"id": "c1", "text": "Policy covers refunds and shipping windows only."}]
        result = check_grounding_assertion(
            response,
            {
                "unsupported_claims_max": 0,
                "contradicted_claims_max": 0,
                "grounding_score_min": 1.0,
            },
            context,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.details["summary"]["insufficient_evidence"], 1)

    def test_citation_required_failure(self) -> None:
        response = LLMResponse(text="Refunds above $100 need manager approval.", structured=None, metadata={})
        context = [{"id": "c1", "text": "Refunds above $100 need manager approval."}]
        result = check_grounding_assertion(
            response,
            {
                "require_citations": True,
                "unsupported_claims_max": 0,
                "contradicted_claims_max": 0,
                "grounding_score_min": 1.0,
            },
            context,
        )
        self.assertFalse(result.passed)
        self.assertIn("citation", result.details["claims"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
