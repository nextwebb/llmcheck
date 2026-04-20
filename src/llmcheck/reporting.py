from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def write_run_junit(payload: dict, out_path: Path) -> None:
    testsuite = Element("testsuite")
    testsuite.set("name", "llmcheck")
    testsuite.set("tests", str(payload.get("counts", {}).get("total_cases", 0)))
    testsuite.set("failures", str(payload.get("counts", {}).get("failed_cases", 0)))

    for suite, cases in payload.get("suites", {}).items():
        for case in cases:
            testcase = SubElement(testsuite, "testcase")
            testcase.set("classname", suite)
            testcase.set("name", str(case.get("case_id")))
            latency_ms = case.get("latency_ms")
            if isinstance(latency_ms, int):
                testcase.set("time", f"{latency_ms / 1000.0:.3f}")
            if not case.get("passed"):
                failure = SubElement(testcase, "failure")
                messages: list[str] = []
                for check in case.get("checks", []):
                    if not check.get("passed"):
                        messages.append(f"{check.get('check_type')}: {check.get('message')}")
                failure.text = "\n".join(messages)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tostring(testsuite, encoding="unicode"), encoding="utf-8")


def write_compare_junit(payload: dict, out_path: Path) -> None:
    matrix = payload.get("matrix", [])
    failures = sum(1 for row in matrix if not row.get("passed"))

    testsuite = Element("testsuite")
    testsuite.set("name", "llmcheck-compare")
    testsuite.set("tests", str(len(matrix)))
    testsuite.set("failures", str(failures))

    for row in matrix:
        testcase = SubElement(testsuite, "testcase")
        testcase.set("classname", f"{row.get('variant')}::{row.get('suite')}")
        testcase.set("name", str(row.get("case_id")))
        latency_ms = row.get("latency_ms")
        if isinstance(latency_ms, int):
            testcase.set("time", f"{latency_ms / 1000.0:.3f}")
        if not row.get("passed"):
            failure = SubElement(testcase, "failure")
            failure.text = (
                f"grounding_score={row.get('grounding_score')} "
                f"unsupported_claims={row.get('unsupported_claims')} "
                f"contradicted_claims={row.get('contradicted_claims')} "
                f"tool_violations={row.get('tool_violations')} "
                f"error={row.get('error')}"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tostring(testsuite, encoding="unicode"), encoding="utf-8")
