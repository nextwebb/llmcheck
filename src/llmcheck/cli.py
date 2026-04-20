from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .compare import CompareExecutionError, execute_compare
from .config import ConfigError, load_cases, load_config
from .dashboard import serve_dashboard
from .models import VariantSpec
from .reporting import write_compare_junit, write_run_junit
from .runner import RunExecutionError, execute_run


def _default_report_path(root: Path) -> Path:
    return root / ".llmcheck" / "reports" / "latest.json"


def _default_compare_report_path(root: Path) -> Path:
    return root / ".llmcheck" / "reports" / "compare-latest.json"


def _default_baseline_root(root: Path) -> Path:
    return root / ".llmcheck" / "baselines"


def _default_report_dir(root: Path) -> Path:
    return root / ".llmcheck" / "reports"


def _print_run_summary(result: dict, *, title: str = "LLMCheck") -> None:
    counts = result["counts"]
    print(f"{title}: {'PASS' if result['passed'] else 'FAIL'}")
    print(
        f"cases {counts['passed_cases']}/{counts['total_cases']} passed | "
        f"checks {counts['total_checks'] - counts['failed_checks']}/{counts['total_checks']} passed"
    )
    if counts.get("runtime_error_cases", 0):
        print(f"runtime errors: {counts['runtime_error_cases']}")

    for suite, cases in result["suites"].items():
        suite_failed = sum(1 for c in cases if not c["passed"])
        print(f"suite {suite}: {'PASS' if suite_failed == 0 else 'FAIL'} ({len(cases) - suite_failed}/{len(cases)} cases)")
        for case in cases:
            if case["passed"]:
                continue
            print(f"  - case {case['case_id']}: FAIL")
            for check in case["checks"]:
                if not check["passed"]:
                    print(f"      * {check['check_type']}: {check['message']}")


def _run_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    report_path = _default_report_path(config.root_dir)
    baseline_root = _default_baseline_root(config.root_dir)

    try:
        run = execute_run(
            config=config,
            suite_filter=args.suite,
            repeats_override=args.repeats,
            update_baseline=args.update_baseline,
            report_path=report_path,
            baseline_root=baseline_root,
            diff_mode=False,
        )
    except RunExecutionError as exc:
        print(f"runtime error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "passed": run.passed,
        "counts": run.counts,
        "suites": {k: [c.__dict__ | {"checks": [ck.__dict__ for ck in c.checks]} for c in v] for k, v in run.suites.items()},
    }
    if args.junit:
        write_run_junit(payload, Path(args.junit).resolve())
    _print_run_summary(payload)
    if run.counts.get("runtime_error_cases", 0) > 0:
        return 2
    return 0 if run.passed else 1


def _list_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
        cases = load_cases(config, args.suite)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    grouped: dict[str, list[str]] = {}
    for case in cases:
        grouped.setdefault(case.suite, []).append(case.id)

    for suite, ids in grouped.items():
        print(f"{suite} ({len(ids)} cases)")
        for case_id in ids:
            print(f"  - {case_id}")
    return 0


def _diff_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    report_path = _default_report_path(config.root_dir)
    baseline_root = _default_baseline_root(config.root_dir)

    try:
        run = execute_run(
            config=config,
            suite_filter=args.suite,
            repeats_override=args.repeats,
            update_baseline=False,
            report_path=report_path,
            baseline_root=baseline_root,
            diff_mode=True,
        )
    except RunExecutionError as exc:
        print(f"runtime error: {exc}", file=sys.stderr)
        return 2

    payload = {
        "passed": run.passed,
        "counts": run.counts,
        "suites": {k: [c.__dict__ | {"checks": [ck.__dict__ for ck in c.checks]} for c in v] for k, v in run.suites.items()},
    }
    _print_run_summary(payload, title="LLMCheck Diff")
    if run.counts.get("runtime_error_cases", 0) > 0:
        return 2
    return 0 if run.passed else 1


def _serve_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    report_dir = _default_report_dir(config.root_dir)
    serve_dashboard(report_dir=report_dir, host=args.host, port=args.port)
    return 0


def _parse_variant_flag(raw: str) -> VariantSpec:
    # format: name=provider:model
    if "=" not in raw or ":" not in raw:
        raise ValueError(f"invalid --variant `{raw}`. expected name=provider:model")
    name, rest = raw.split("=", 1)
    provider, model = rest.split(":", 1)
    name = name.strip()
    provider = provider.strip()
    model = model.strip()
    if not name or not provider or not model:
        raise ValueError(f"invalid --variant `{raw}`. expected name=provider:model")
    return VariantSpec(name=name, provider=provider, model=model)


def _print_compare_summary(report: dict) -> None:
    print(f"LLMCheck Compare: {'PASS' if report.get('passed') else 'FAIL'}")
    print(f"variants: {', '.join(report.get('variants', []))}")
    print("variant | suite | case | pass | grounding | unsupported | contradicted | tool_violations | latency_ms | total_tokens")
    for row in report.get("matrix", []):
        cost = row.get("cost_estimate") or {}
        print(
            f"{row.get('variant')} | {row.get('suite')} | {row.get('case_id')} | "
            f"{row.get('passed')} | {row.get('grounding_score')} | {row.get('unsupported_claims')} | "
            f"{row.get('contradicted_claims')} | {row.get('tool_violations')} | "
            f"{row.get('latency_ms')} | {cost.get('total_tokens')}"
        )


def _compare_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
        cases = load_cases(config, args.suite)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    variants: list[VariantSpec] = []
    if args.variant:
        try:
            variants.extend(_parse_variant_flag(v) for v in args.variant)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        variants = list(config.variants)

    report_path = _default_compare_report_path(config.root_dir)
    baseline_root = _default_baseline_root(config.root_dir)

    try:
        report = execute_compare(
            config=config,
            cases=cases,
            variants=variants,
            repeats_override=args.repeats,
            baseline_root=baseline_root,
            report_path=report_path,
        )
    except CompareExecutionError as exc:
        print(f"compare error: {exc}", file=sys.stderr)
        return 2

    if args.junit:
        write_compare_junit(report, Path(args.junit).resolve())
    _print_compare_summary(report)
    has_runtime_errors = any(row.get("error") for row in report.get("matrix", []))
    if has_runtime_errors:
        return 2
    return 0 if report.get("passed") else 1


def _doctor_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 2

    print("LLMCheck doctor")
    print(f"config: {config_path}")
    ok = True

    for provider_name, provider_cfg in config.providers.items():
        env = provider_cfg.api_key_env
        exists = bool(os.getenv(env))
        print(f"provider {provider_name}: env {env} {'set' if exists else 'missing'}")
        if not exists:
            ok = False

    try:
        cases = load_cases(config, args.suite)
        print(f"case discovery: ok ({len(cases)} cases)")
    except ConfigError as exc:
        print(f"case discovery: failed ({exc})")
        return 2

    return 0 if ok else 1


def _init_command(args: argparse.Namespace) -> int:
    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "llmcheck.yaml"
    cases_dir = root / "examples" / "cases"
    sample_case = cases_dir / "sample_grounding_and_tool.yaml"

    if not config_path.exists():
        config_path.write_text(
            """providers:
  openai:
    api_key_env: OPENAI_API_KEY
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
  gemini:
    api_key_env: GEMINI_API_KEY

suites:
  - name: default
    cases:
      - examples/cases/*.yaml

variants:
  - name: openai-mini
    provider: openai
    model: gpt-4.1-mini
  - name: claude-sonnet
    provider: anthropic
    model: claude-3-5-sonnet-latest
""",
            encoding="utf-8",
        )

    cases_dir.mkdir(parents=True, exist_ok=True)
    if not sample_case.exists():
        sample_case.write_text(
            """id: sample_grounding_and_tool
provider: openai
model: gpt-4.1-mini
messages:
  - role: user
    content: |
      Summarize policy and mention if approval is required.
context_chunks:
  - id: policy-1
    text: "Refunds above $100 require manager approval."
trace_events:
  - tool: retrieve_policy
    arguments:
      policy_id: refunds
assertions:
  - type: grounding_assertion
    require_citations: false
    unsupported_claims_max: 0
    contradicted_claims_max: 0
    grounding_score_min: 0.5
  - type: tool_contract
    required_tools: [retrieve_policy]
""",
            encoding="utf-8",
        )

    print(f"initialized {config_path}")
    print(f"created sample case {sample_case}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmcheck", description="LLM regression and contract checks for local and CI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="create minimal llmcheck config and sample case")
    init_cmd.add_argument("--dir", default=".")
    init_cmd.set_defaults(handler=_init_command)

    run_cmd = sub.add_parser("run", help="run configured suites and checks")
    run_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    run_cmd.add_argument("--suite", default=None)
    run_cmd.add_argument("--repeats", type=int, default=None)
    run_cmd.add_argument("--update-baseline", action="store_true")
    run_cmd.add_argument("--junit", default=None, help="optional junit xml output path")
    run_cmd.set_defaults(handler=_run_command)

    list_cmd = sub.add_parser("list", help="list discovered suites and cases")
    list_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    list_cmd.add_argument("--suite", default=None)
    list_cmd.set_defaults(handler=_list_command)

    diff_cmd = sub.add_parser("diff", help="run only baseline diff checks")
    diff_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    diff_cmd.add_argument("--suite", default=None)
    diff_cmd.add_argument("--repeats", type=int, default=None)
    diff_cmd.set_defaults(handler=_diff_command)

    compare_cmd = sub.add_parser("compare", help="run same suite across variants and produce deltas")
    compare_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    compare_cmd.add_argument("--suite", default=None)
    compare_cmd.add_argument("--repeats", type=int, default=None)
    compare_cmd.add_argument("--variant", action="append", default=[], help="name=provider:model")
    compare_cmd.add_argument("--junit", default=None, help="optional junit xml output path")
    compare_cmd.set_defaults(handler=_compare_command)

    doctor_cmd = sub.add_parser("doctor", help="validate config, case discovery, and provider env vars")
    doctor_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    doctor_cmd.add_argument("--suite", default=None)
    doctor_cmd.set_defaults(handler=_doctor_command)

    serve_cmd = sub.add_parser("serve", help="serve report dashboard on localhost")
    serve_cmd.add_argument("-c", "--config", default="llmcheck.yaml")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=9090)
    serve_cmd.set_defaults(handler=_serve_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = args.handler(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
