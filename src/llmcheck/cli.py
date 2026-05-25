from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, load_config
from .generation import (
    append_case_to_suite,
    draft_regression_case,
    dump_regression_case,
    initialize_suite_file,
    validate_regression_case_yaml,
)
from .pilot_dashboard import serve_pilot_dashboard
from .pilot import (
    CONFIDENCE_LEVELS,
    IMPACTS,
    KNOWLEDGE_TYPES,
    MISSING_CONTEXT_SUBTYPES,
    REVIEW_OUTCOMES,
    ROOT_CAUSES,
    SEVERITIES,
    USAGE_MODES,
    build_knowledge_entry,
    build_pilot_review,
    export_scorecard,
    infer_workflow,
    review_to_dict,
    summarize_pilot,
    write_pilot_report,
)
from .storage.models import ReviewRecord
from .storage.sqlite import (
    get_run,
    init_db,
    list_knowledge_entries,
    list_pilot_reviews,
    list_runs,
    save_knowledge_entry,
    save_pilot_review,
    save_review,
)
from .suite_runner import SuiteRunError, run_suite


def _default_config_path() -> Path:
    return Path("llmcheck.yaml").resolve()


def _default_suite_path() -> Path:
    return Path("llmcheck_suite.yaml").resolve()


def _load_app_config(config_arg: str) -> tuple[Path, object]:
    config_path = Path(config_arg).resolve()
    return config_path, load_config(config_path)


def _input_preview(run) -> str:
    value = str(run.input_json.get("user_input") or "").strip()
    return (value[:57] + "...") if len(value) > 60 else value


def _output_preview(run) -> str:
    value = run.output_text.strip()
    return (value[:57] + "...") if len(value) > 60 else value


def _print_run(run) -> None:
    print(f"Run: {run.id}")
    print(f"Created: {run.created_at}")
    print(f"Flagged: {'yes' if run.flagged else 'no'}")
    print(f"Flag reason: {run.flag_reason or '-'}")
    print(f"Input: {run.input_json.get('user_input') or '-'}")
    print("Messages:")
    for message in run.messages:
        print(f"  - {message.get('role', 'unknown')}: {message.get('content', '')}")
    print("Context:")
    if run.context:
        for item in run.context:
            print(f"  - {item.get('id', 'context')}: {item.get('text', '')}")
    else:
        print("  - none")
    print(f"Output: {run.output_text or '-'}")
    print(f"Tags: {run.tags}")
    print(f"Metadata: {run.metadata}")


def _read_correction_text() -> str:
    print("What was wrong, and what should the model have said or avoided?")
    return input("> ").strip()


def _ask_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    joined = "/".join(options)
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt} ({joined}){suffix}: ").strip()
        value = raw or (default or "")
        if value in options:
            return value
        print(f"invalid choice: {value}", file=sys.stderr)


def _ask_bool(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1"}


def _ask_int(prompt: str, default: int = 0) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print(f"invalid integer: {raw}", file=sys.stderr)


def _ask_multi(prompt: str, options: list[str]) -> list[str]:
    raw = input(f"{prompt} (comma-separated from {', '.join(options)}): ").strip()
    if not raw:
        return []
    values = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in values if item not in options]
    if invalid:
        raise ConfigError(f"invalid values: {', '.join(invalid)}")
    return values


def _edit_yaml(initial_text: str) -> str:
    editor = os.getenv("EDITOR")
    if editor:
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as handle:
            handle.write(initial_text)
            handle.flush()
            temp_path = Path(handle.name)
        try:
            subprocess.run([editor, str(temp_path)], check=True)
            return temp_path.read_text(encoding="utf-8")
        finally:
            temp_path.unlink(missing_ok=True)

    print("No $EDITOR configured. Paste the full YAML draft, then submit EOF.")
    lines: list[str] = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass
    return "\n".join(lines).strip() or initial_text


def _select_run(config, run_id: str | None, latest: bool):
    if run_id:
        run = get_run(config.storage.path, run_id)
        if run is None:
            raise ConfigError(f"run not found: {run_id}")
        return run
    if latest:
        flagged_runs = list_runs(config.storage.path, flagged=True, limit=1)
        if flagged_runs:
            return flagged_runs[0]
        recent_runs = list_runs(config.storage.path, flagged=False, limit=1)
        if recent_runs:
            print("warning: no flagged runs found; falling back to latest run", file=sys.stderr)
            return recent_runs[0]
    raise ConfigError("review requires <run_id> or --latest")


def _init_command(args: argparse.Namespace) -> int:
    root = Path(args.dir).resolve()
    llmcheck_dir = root / ".llmcheck"
    llmcheck_dir.mkdir(parents=True, exist_ok=True)
    init_db(llmcheck_dir / "llmcheck.db")

    config_path = root / "llmcheck.yaml"
    if config_path.exists() and not args.force:
        print(f"exists: {config_path}")
    else:
        config_path.write_text(
            "storage:\n  path: .llmcheck/llmcheck.db\njudge:\n  provider: openai\n  model: gpt-4o-mini\n",
            encoding="utf-8",
        )
        print(f"created: {config_path}")

    suite_path = root / "llmcheck_suite.yaml"
    if suite_path.exists() and not args.force:
        print(f"exists: {suite_path}")
    else:
        initialize_suite_file(suite_path, force=True)
        print(f"created: {suite_path}")
    return 0


def _list_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    runs = list_runs(config.storage.path, flagged=args.flagged, limit=args.limit)
    print("run_id | created_at | flagged | reason | input | output")
    for run in runs:
        print(
            f"{run.id} | {run.created_at} | {'yes' if run.flagged else 'no'} | "
            f"{run.flag_reason or '-'} | {_input_preview(run)} | {_output_preview(run)}"
        )
    return 0


def _show_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    run = get_run(config.storage.path, args.run_id)
    if run is None:
        print(f"run not found: {args.run_id}", file=sys.stderr)
        return 2
    _print_run(run)
    return 0


def _review_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    run = _select_run(config, args.run_id, args.latest)
    _print_run(run)

    correction_text = _read_correction_text()
    if not correction_text:
        print("review aborted: correction text is required", file=sys.stderr)
        return 2

    draft = draft_regression_case(run, correction_text)
    draft_yaml = dump_regression_case(draft)
    print("\nDraft YAML:\n")
    print(draft_yaml)

    action = input("[A]pprove, [E]dit, [R]eject? ").strip().lower() or "a"
    status = "rejected"
    final_yaml = draft_yaml
    if action.startswith("e"):
        final_yaml = _edit_yaml(draft_yaml)
        validate_regression_case_yaml(final_yaml)
        action = "a"
    if action.startswith("a"):
        case = validate_regression_case_yaml(final_yaml)
        append_case_to_suite(Path(args.suite).resolve(), case)
        status = "approved"
        print(f"saved test: {case['id']}")
    elif not action.startswith("r"):
        print("review aborted: invalid action", file=sys.stderr)
        return 2

    save_review(
        config.storage.path,
        ReviewRecord(
            id=f"review_{uuid.uuid4().hex[:12]}",
            run_id=run.id,
            created_at=datetime.now(timezone.utc).isoformat(),
            correction_text=correction_text,
            generated_yaml=final_yaml,
            status=status,
        ),
    )
    return 0


def _pilot_review_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    run = _select_run(config, args.run_id, args.latest)
    _print_run(run)
    print()
    print("Pilot review taxonomy")
    workflow = infer_workflow(run)
    print(f"Workflow inferred: {workflow}")
    severity = _ask_choice("Severity", SEVERITIES, default="medium")
    issue_class_guess = input("Issue class guess [unknown]: ").strip() or "unknown"
    root_cause = _ask_choice("Root cause", ROOT_CAUSES)
    missing_context_subtype = None
    if root_cause == "missing_context":
        missing_context_subtype = _ask_choice("Missing-context subtype", MISSING_CONTEXT_SUBTYPES)
    review_outcome = _ask_choice("Review outcome", REVIEW_OUTCOMES, default="confirmed_failure")
    reusable_pattern = _ask_bool("Reusable pattern?", default=(review_outcome == "confirmed_failure"))
    business_impact = _ask_choice("Business impact", IMPACTS, default="medium")
    candidate_knowledge_type = _ask_choice("Candidate knowledge type", KNOWLEDGE_TYPES, default="none")
    knowledge_approved = False
    usage_modes: list[str] = []
    if candidate_knowledge_type != "none":
        knowledge_approved = _ask_bool("Approve this knowledge candidate?", default=False)
        if knowledge_approved:
            usage_modes = _ask_multi("Approved usage modes", USAGE_MODES)
    repeat_pattern_seen_before = _ask_bool("Repeat pattern seen before?", default=False)
    similar_prior_incident_count = _ask_int("Similar prior incident count", default=0)
    time_to_review_minutes = _ask_int("Time to review (minutes)", default=5)
    time_to_operationalize_minutes = _ask_int("Time to operationalize (minutes)", default=10)
    recurrence_within_14d = _ask_bool("Recurrence within 14d?", default=False)
    recurrence_within_30d = _ask_bool("Recurrence within 30d?", default=False)
    avoided_after_intervention = _ask_bool("Avoided after intervention?", default=False)
    reviewer_note = input("Reviewer note: ").strip()

    review = build_pilot_review(
        run,
        severity=severity,
        issue_class_guess=issue_class_guess,
        root_cause=root_cause,
        missing_context_subtype=missing_context_subtype,
        review_outcome=review_outcome,
        business_impact=business_impact,
        candidate_knowledge_type=candidate_knowledge_type,
        reviewer_note=reviewer_note,
        reusable_pattern=reusable_pattern,
        knowledge_approved=knowledge_approved,
        approved_usage_modes=usage_modes,
        repeat_pattern_seen_before=repeat_pattern_seen_before,
        similar_prior_incident_count=similar_prior_incident_count,
        time_to_review_minutes=time_to_review_minutes,
        time_to_operationalize_minutes=time_to_operationalize_minutes,
        recurrence_within_14d=recurrence_within_14d,
        recurrence_within_30d=recurrence_within_30d,
        avoided_after_intervention=avoided_after_intervention,
    )
    save_pilot_review(config.storage.path, review)
    print(json.dumps(review_to_dict(review), indent=2))

    if candidate_knowledge_type != "none" and knowledge_approved:
        title = input("Knowledge title: ").strip() or f"{candidate_knowledge_type}:{run.id}"
        body = input("Knowledge body: ").strip() or reviewer_note or (run.flag_reason or run.output_text)
        confidence = _ask_choice("Knowledge confidence", CONFIDENCE_LEVELS, default="high")
        entry = build_knowledge_entry(run, review, title=title, body=body, confidence=confidence)
        save_knowledge_entry(config.storage.path, entry)
        print(f"saved knowledge entry: {entry.id}")

    return 0


def _pilot_scorecard_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    reviews = list_pilot_reviews(config.storage.path, limit=args.limit)
    export_path = Path(args.output).resolve()
    export_scorecard(export_path, reviews)
    print(f"wrote scorecard: {export_path}")
    print(f"reviews exported: {len(reviews)}")
    return 0


def _pilot_report_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    reviews = list_pilot_reviews(config.storage.path, limit=args.limit)
    report_path = Path(args.output).resolve()
    write_pilot_report(report_path, reviews)
    summary = summarize_pilot(reviews)
    print(f"wrote pilot report: {report_path}")
    print(
        f"reviews={summary['total_reviews']} confirmed={summary['confirmed_failures']} "
        f"missing_context_share={summary['missing_context_share']:.0%} "
        f"reusable_pattern_share={summary['reusable_pattern_share']:.0%} "
        f"knowledge_approval_rate={summary['knowledge_approval_rate']:.0%}"
    )
    return 0


def _pilot_knowledge_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    entries = list_knowledge_entries(config.storage.path, limit=args.limit)
    print("knowledge_id | created_at | type | status | confidence | usage_modes | title")
    for item in entries:
        print(
            f"{item.id} | {item.created_at} | {item.knowledge_type} | {item.status} | "
            f"{item.confidence} | {','.join(item.usage_modes)} | {item.title}"
        )
    return 0


def _pilot_dashboard_command(args: argparse.Namespace) -> int:
    _, config = _load_app_config(args.config)
    serve_pilot_dashboard(config.storage.path, host=args.host, port=args.port)
    return 0


def _run_suite_command(args: argparse.Namespace) -> int:
    try:
        _, config = _load_app_config(args.config)
        result = run_suite(config, Path(args.suite).resolve())
    except (ConfigError, SuiteRunError) as exc:
        print(f"runtime error: {exc}", file=sys.stderr)
        return 2

    print("LLMCheck suite")
    print()
    for item in result.results:
        if item.passed:
            print(f"PASS {item.test_id}")
            print()
            continue
        print(f"FAIL {item.test_id}")
        if item.judge_result.missing_requirements:
            print("  Missing:")
            for value in item.judge_result.missing_requirements:
                print(f'    - "{value}"')
        if item.judge_result.forbidden_claims_found:
            print("  Forbidden found:")
            for value in item.judge_result.forbidden_claims_found:
                print(f'    - "{value}"')
        if item.judge_result.unsupported_claims:
            print("  Unsupported:")
            for value in item.judge_result.unsupported_claims:
                print(f'    - "{value}"')
        print()
    return 0 if result.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmcheck", description="Turn bad LLM/RAG runs into regression checks.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init")
    init_parser.add_argument("--dir", default=".")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=_init_command)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    list_parser.add_argument("--flagged", action="store_true")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.set_defaults(func=_list_command)

    show_parser = sub.add_parser("show")
    show_parser.add_argument("run_id")
    show_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    show_parser.set_defaults(func=_show_command)

    review_parser = sub.add_parser("review")
    review_parser.add_argument("run_id", nargs="?")
    review_parser.add_argument("--latest", action="store_true")
    review_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    review_parser.add_argument("--suite", default=str(_default_suite_path()))
    review_parser.set_defaults(func=_review_command)

    suite_parser = sub.add_parser("run-suite")
    suite_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    suite_parser.add_argument("--suite", default=str(_default_suite_path()))
    suite_parser.set_defaults(func=_run_suite_command)

    pilot_review_parser = sub.add_parser("pilot-review")
    pilot_review_parser.add_argument("run_id", nargs="?")
    pilot_review_parser.add_argument("--latest", action="store_true")
    pilot_review_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    pilot_review_parser.set_defaults(func=_pilot_review_command)

    pilot_scorecard_parser = sub.add_parser("pilot-scorecard")
    pilot_scorecard_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    pilot_scorecard_parser.add_argument("--output", default=".llmcheck/pilot-scorecard.csv")
    pilot_scorecard_parser.add_argument("--limit", type=int, default=500)
    pilot_scorecard_parser.set_defaults(func=_pilot_scorecard_command)

    pilot_report_parser = sub.add_parser("pilot-report")
    pilot_report_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    pilot_report_parser.add_argument("--output", default=".llmcheck/pilot-report.md")
    pilot_report_parser.add_argument("--limit", type=int, default=500)
    pilot_report_parser.set_defaults(func=_pilot_report_command)

    pilot_knowledge_parser = sub.add_parser("pilot-knowledge")
    pilot_knowledge_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    pilot_knowledge_parser.add_argument("--limit", type=int, default=200)
    pilot_knowledge_parser.set_defaults(func=_pilot_knowledge_command)

    pilot_dashboard_parser = sub.add_parser("pilot-dashboard")
    pilot_dashboard_parser.add_argument("-c", "--config", default=str(_default_config_path()))
    pilot_dashboard_parser.add_argument("--host", default="127.0.0.1")
    pilot_dashboard_parser.add_argument("--port", type=int, default=8765)
    pilot_dashboard_parser.set_defaults(func=_pilot_dashboard_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
