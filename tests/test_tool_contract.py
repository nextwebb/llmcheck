from __future__ import annotations

import unittest

from llmcheck.checks import check_tool_contract


class ToolContractTests(unittest.TestCase):
    def test_required_tool_missing(self) -> None:
        events = [{"index": 0, "tool": "finalize", "arguments": {}}]
        result = check_tool_contract(events, {"required_tools": ["retrieve_policy"]})
        self.assertFalse(result.passed)

    def test_forbidden_tool_used(self) -> None:
        events = [{"index": 0, "tool": "issue_refund", "arguments": {}}]
        result = check_tool_contract(events, {"forbidden_tools": ["issue_refund"]})
        self.assertFalse(result.passed)

    def test_ordering_violation(self) -> None:
        events = [
            {"index": 0, "tool": "issue_refund", "arguments": {}},
            {"index": 1, "tool": "retrieve_policy", "arguments": {}},
        ]
        result = check_tool_contract(events, {"required_before": [{"first": "retrieve_policy", "then": "issue_refund"}]})
        self.assertFalse(result.passed)

    def test_argument_assertion_failure(self) -> None:
        events = [{"index": 0, "tool": "create_ticket", "arguments": {"priority": "low"}}]
        result = check_tool_contract(
            events,
            {
                "argument_assertions": [
                    {"tool": "create_ticket", "path": "priority", "equals": "high"},
                ]
            },
        )
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
