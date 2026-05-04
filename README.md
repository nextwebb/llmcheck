# LLMCheck

LLMCheck is a lightweight installable CLI for measurable LLM/agent checks in local dev and CI.

It focuses on bounded, testable failure modes:
- schema and contract violations
- grounding failures against provided context
- tool/process trace contract violations
- repeated-run instability
- variant regressions across provider/model/prompt settings

It does **not** claim open-world truth verification.

## Install

```bash
python3 -m pip install -e .
```

## API Keys

Set only the providers you use:

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GEMINI_API_KEY="..."
```

## Commands

```bash
llmcheck init --dir .
llmcheck doctor -c llmcheck.yaml
llmcheck list -c llmcheck.yaml
llmcheck run -c llmcheck.yaml
llmcheck diff -c llmcheck.yaml
llmcheck compare -c llmcheck.yaml
```

## Agentic Workflow POC

A local-first single-agent chat POC is available in `apps/agentic-poc`.

- Backend run: `make agentic-poc-backend`
- Frontend run: `make agentic-poc-frontend`
- Testing guide: `docs/agentic-poc-testing.md`

Optional JUnit output:

```bash
llmcheck run -c llmcheck.yaml --junit .llmcheck/reports/junit.xml
llmcheck compare -c llmcheck.yaml --junit .llmcheck/reports/compare-junit.xml
```

## Compare Variants

Define variants in `llmcheck.yaml`:

```yaml
variants:
  - name: openai-mini
    provider: openai
    model: gpt-4.1-mini
  - name: claude-sonnet
    provider: anthropic
    model: claude-3-5-sonnet-latest
```

Or pass variants on CLI:

```bash
llmcheck compare -c llmcheck.yaml \
  --variant oai=openai:gpt-4.1-mini \
  --variant claude=anthropic:claude-3-5-sonnet-latest
```

Compare writes `.llmcheck/reports/compare-latest.json` and timestamped compare snapshots.

## Case Format (MVP)

```yaml
id: grounding_and_tool_contract
provider: openai
model: gpt-4.1-mini
messages:
  - role: user
    content: "Summarize refund policy"
context_chunks:
  - id: policy-1
    text: "Refunds above $100 require manager approval."
trace_events:
  - tool: retrieve_policy
    arguments: { policy_id: refund }
assertions:
  - type: grounding_assertion
    require_citations: false
    unsupported_claims_max: 0
    contradicted_claims_max: 0
    grounding_score_min: 0.6
  - type: tool_contract
    required_tools: [retrieve_policy]
    required_before:
      - first: retrieve_policy
        then: issue_refund
    argument_assertions:
      - tool: retrieve_policy
        path: policy_id
        equals: refund
```

## `grounding_assertion`

Supported parameters:
- `require_citations` (bool)
- `claims` (list[str]) or `claims_json_path` (string)
- `unsupported_claims_max` (int)
- `contradicted_claims_max` (int)
- `grounding_score_min` (float)

Output includes per-claim classification:
- `supported`
- `contradicted`
- `insufficient_evidence`

## `tool_contract`

Supported rules:
- `required_tools`
- `forbidden_tools`
- `required_before`
- `required_after`
- `ordered_sequence`
- `argument_assertions`
- `confirmation_required_before_write_action`

## Reports

- Run report: `.llmcheck/reports/latest.json`
- Compare report: `.llmcheck/reports/compare-latest.json`
- Timestamped snapshots: `.llmcheck/reports/report-<timestamp>.json`, `.llmcheck/reports/compare-<timestamp>.json`

## Exit Codes

- `0`: checks passed
- `1`: gate failure
- `2`: config/runtime/infra issue

## CI (GitHub Actions)

Use `.github/workflows/llmcheck.yml` as baseline and run:

```bash
llmcheck run -c llmcheck.yaml
llmcheck compare -c llmcheck.yaml
```
