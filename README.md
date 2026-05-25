# LLMCheck

LLMCheck is a local-first tool for turning real LLM/RAG failures into something operational.

Today, it has two connected workflows:

1. `capture -> review -> YAML regression check -> replay`
2. `capture -> pilot review -> approved knowledge -> controlled reuse`

The product claim is intentionally narrow:

> LLMCheck does not prove an answer is true.
> It helps you capture bad runs, review them, operationalize them, and reduce repeated failures.

It is not:

- a hosted observability platform
- a general-purpose agent framework
- a dashboard for every possible LLM metric
- a proof system for correctness
- automatic prompt repair

The current codebase is best understood as an open-source local core. If you later offer a hosted version, this README should still be true for the local product on its own.

## Demo

![LLMCheck demo](docs/assets/llmcheck-demo.gif)

## What Exists Today

LLMCheck currently supports:

- OpenAI Python SDK instrumentation via `instrument_openai(...)`
- local SQLite storage at `.llmcheck/llmcheck.db`
- explicit context capture with `add_context(...)`
- explicit tags with `add_tags(...)`
- post-response run flagging with `flag(...)`
- CLI inspection of captured runs
- human review into YAML regression checks
- replay of approved YAML checks via a Python callable
- pilot review taxonomy for testing the "missing context" thesis
- approved knowledge entries with usage modes
- local pilot dashboard for `pilot_reviews` and `knowledge_entries`
- controlled knowledge reuse on later runs

Current scope is deliberately narrow:

- only the OpenAI Python client is instrumented
- only `client.chat.completions.create(...)` is wrapped
- storage is local SQLite only
- the pilot dashboard is a local HTTP server, not a hosted multi-user app
- knowledge reuse is workflow-scoped and conservative

## How To Think About The Product

There are two different but related loops.

### 1. Regression Loop

Use this when you already know a run was bad and you want to stop repeating the same failure in development or CI.

Flow:

`bad run -> review -> YAML check -> replay -> pass/fail`

### 2. Pilot Knowledge Loop

Use this when you want to test whether your failures are actually caused by missing or misrouted context, and whether reviewed knowledge can help later runs.

Flow:

`captured run -> pilot review -> knowledge approval -> later run reuse -> inspect recurrence`

The pilot loop is the more experimental part of the product. It exists to test a business thesis, not to pretend the system can generally "learn" from everything.

## Install

Install LLMCheck into the same Python environment as your app:

```bash
python -m pip install -e .
```

If your app does not already depend on the OpenAI Python SDK, install `openai` in that environment too.

## Quick Start

### 1. Initialize a workspace

```bash
llmcheck init
```

This creates:

- `.llmcheck/llmcheck.db`
- `llmcheck.yaml`
- `llmcheck_suite.yaml`

Default `llmcheck.yaml`:

```yaml
storage:
  path: .llmcheck/llmcheck.db

judge:
  provider: openai
  model: gpt-4o-mini
```

Important detail:

`storage.path` is resolved relative to the directory containing `llmcheck.yaml`.

### 2. Instrument your OpenAI client

```python
from openai import OpenAI
from llmcheck import instrument_openai

client = instrument_openai(OpenAI())
```

This wraps the existing client in place and preserves the normal return value from `client.chat.completions.create(...)`.

Current V1 precision:

- it captures only `chat.completions.create`
- it writes a run to SQLite after the call returns
- it does not replace your app architecture or runtime

### 3. Attach context and tags before the call

```python
from llmcheck import add_context, add_tags

docs = [
    {"id": "policy-1", "text": "Refunds above $100 require manager approval."},
    {"id": "policy-2", "text": "Refunds take 3-5 business days."},
]

add_context(docs)
add_tags({"workflow": "refund-bot", "session_id": "abc123"})
```

### 4. Make the model call

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a support agent."},
        {"role": "user", "content": "Can I get a refund above $100?"},
    ],
)
```

### 5. Flag a bad run if needed

```python
from llmcheck import flag

text = response.choices[0].message.content
if "instant" in text.lower():
    flag(reason="claimed instant refund")
```

### 6. Inspect the captured run

```bash
llmcheck list --flagged
llmcheck show run_123
```

### 7. Turn it into a regression case

```bash
llmcheck review run_123
```

Or:

```bash
llmcheck review --latest
```

### 8. Replay the suite

```bash
llmcheck run-suite -c llmcheck.yaml --suite llmcheck_suite.yaml
```

## Public Python API

LLMCheck currently exposes exactly four public helpers:

```python
from llmcheck import instrument_openai, add_context, add_tags, flag
```

### `instrument_openai(client, *, storage_path=None)`

Wrap an existing OpenAI client.

What it does:

- captures `model`
- captures `messages`
- extracts the last user message as `user_input` when possible
- captures output text from `choices[0].message.content`
- captures usage data if present
- records latency in milliseconds
- records pending context and tags
- records applied knowledge entries if retrieval policy injection occurs
- saves the run to SQLite

What it does not do:

- it does not intercept every OpenAI SDK feature
- it does not stream partial tokens into storage
- it does not manage API keys
- it does not send data to an LLMCheck service

`storage_path`:

- if provided, that SQLite path is used directly
- if omitted, the default is `.llmcheck/llmcheck.db` resolved from the process working directory

That last point matters. If your app process does not run from the project root, pass `storage_path` explicitly or ensure the working directory is intentional.

### `add_context(docs)`

Attach context to the next captured run in the current context.

Accepted shapes:

```python
add_context(["chunk one", "chunk two"])
```

```python
add_context([
    {"id": "policy-1", "text": "Refunds above $100 require manager approval."}
])
```

Normalization:

```json
[
  {"id": "context-1", "text": "chunk one"},
  {"id": "context-2", "text": "chunk two"}
]
```

Current behavior:

- uses `contextvars`
- does not crash if called before any run exists
- applies to the next captured call in that context
- is cleared after that captured call

### `add_tags(tags)`

Attach JSON-serializable metadata to the next captured run in the current context.

Example:

```python
add_tags({"workflow": "refund-bot", "session_id": "abc123"})
```

Current behavior:

- merges into pending tags
- applies to the next captured call in that context
- is cleared after that captured call

### `flag(reason)`

Flag the most recent captured run in the current context.

Example:

```python
response = client.chat.completions.create(...)
if bad_condition:
    flag(reason="bad_answer")
```

Current behavior:

- marks the last captured run in the current context as flagged
- writes `flagged=1` and `flag_reason=<reason>` into SQLite
- prints a warning to stderr if no captured run is available to flag

## What Gets Stored

Captured runs are stored in `.llmcheck/llmcheck.db` by default.

The current SQLite database contains:

- `runs`
- `reviews`
- `pilot_reviews`
- `knowledge_entries`

### `runs`

Each run stores:

- `id`
- `created_at`
- `name`
- `input_json`
- `output_text`
- `messages_json`
- `context_json`
- `tags_json`
- `metadata_json`
- `flagged`
- `flag_reason`

### `reviews`

Used by the regression-check workflow.

Each review stores:

- `run_id`
- `correction_text`
- `generated_yaml`
- `status`

### `pilot_reviews`

Used by the pilot workflow that tests whether reviewed missing-context knowledge is actually useful.

Each pilot review stores:

- workflow
- severity
- detector sources
- issue class guess
- root cause
- missing-context subtype
- review outcome
- reusable pattern flag
- business impact
- candidate knowledge type
- approval status
- approved usage modes
- repeat-pattern info
- review time
- operationalization time
- recurrence fields
- reviewer note

### `knowledge_entries`

Used by the pilot knowledge loop.

Each knowledge entry stores:

- source run id
- source review id
- knowledge type
- title
- body
- scope
- confidence
- usage modes
- status

## CLI Reference

### `llmcheck init`

Create the default local files.

```bash
llmcheck init
llmcheck init --dir /path/to/project
llmcheck init --force
```

### `llmcheck list`

Show recent runs.

```bash
llmcheck list
llmcheck list --flagged
llmcheck list --limit 50
llmcheck list -c llmcheck.yaml
```

### `llmcheck show <run_id>`

Print one captured run in detail.

```bash
llmcheck show run_123
```

Current output includes:

- input
- messages
- context
- output
- tags
- metadata
- flag status

### `llmcheck review <run_id>`

Review a run into a YAML regression case.

```bash
llmcheck review run_123
llmcheck review --latest
```

Review flow:

1. load the run
2. print input/messages/context/output/tags/metadata/flag
3. ask what was wrong
4. draft YAML
5. approve, edit, or reject

If approved:

- the test is appended to `llmcheck_suite.yaml`
- a review record is written to SQLite

### `llmcheck run-suite`

Replay approved YAML checks.

```bash
llmcheck run-suite
llmcheck run-suite -c llmcheck.yaml --suite llmcheck_suite.yaml
```

Exit codes:

- `0`: all tests passed
- `1`: one or more tests failed
- `2`: config, import, runtime, or judge error

### `llmcheck pilot-review`

Run the structured pilot review flow.

```bash
llmcheck pilot-review run_123
llmcheck pilot-review --latest
```

This is not the same as `review`.

`pilot-review` exists to help you answer business questions like:

- was this failure really caused by missing context?
- is the failure reusable?
- is the reviewed knowledge safe enough to keep?

### `llmcheck pilot-scorecard`

Export pilot review data to CSV.

```bash
llmcheck pilot-scorecard
llmcheck pilot-scorecard --output .llmcheck/pilot-scorecard.csv
```

### `llmcheck pilot-report`

Write a short markdown report from pilot review data.

```bash
llmcheck pilot-report
llmcheck pilot-report --output .llmcheck/pilot-report.md
```

The current report summarizes:

- total reviews
- confirmed failures
- missing-context share
- reusable-pattern share
- knowledge approval rate
- repeat-pattern share
- recurrence rates

### `llmcheck pilot-knowledge`

List current knowledge entries.

```bash
llmcheck pilot-knowledge
```

### `llmcheck pilot-dashboard`

Start the local pilot dashboard.

```bash
llmcheck pilot-dashboard
llmcheck pilot-dashboard --host 127.0.0.1 --port 8765
```

Current behavior:

- serves local HTML at `/`
- serves JSON at `/api/pilot`
- displays summary metrics, recent `pilot_reviews`, and `knowledge_entries`
- reads only local SQLite data

This is a local dashboard, not a hosted review queue.

## Regression Check Workflow

Use this when you want CI or local replay to prevent a known failure from recurring.

### Step 1. Capture a real bad run

Instrument your app and flag the run if needed.

### Step 2. Review it

```bash
llmcheck review --latest
```

### Step 3. Approve the generated YAML

Approved cases are appended to `llmcheck_suite.yaml`.

Example:

```yaml
runner:
  type: python
  callable: "examples.rag_support_agent:answer_user"

tests:
  - id: refund_policy_missing_approval
    source_run_id: "run_123"
    source_reason: "Model said refund was instant."
    metadata:
      created_at: "2026-05-25T14:30:00Z"
      reviewed_by: "local"
    inputs:
      query: "Can I get a refund above $100?"
    context:
      - id: "policy-1"
        text: "Refunds above $100 require manager approval and take 3-5 business days."
    expected:
      must_include:
        - "manager approval"
      must_not_claim:
        - "instant"
    judge:
      type: rubric
      pass_if: "The answer states manager approval is required and does not claim the refund is instant."
```

### Step 4. Replay the suite

```bash
llmcheck run-suite
```

## How Suite Replay Works

LLMCheck suite replay is intentionally simple.

### Runner

The suite runner currently supports:

```yaml
runner:
  type: python
  callable: "module.path:function_name"
```

During replay, LLMCheck:

1. loads the suite YAML
2. imports the callable
3. invokes it with `test.inputs` as keyword arguments
4. captures the output text
5. sends the output to the judge
6. computes pass/fail in Python

Important detail:

The callable import is resolved relative to the suite file directory, not just the current shell directory.

### Judge

The judge is an LLM used only for structured evidence extraction.

It is not the final authority on pass/fail.

Required JSON shape:

```json
{
  "missing_requirements": [],
  "forbidden_claims_found": [],
  "unsupported_claims": [],
  "reason": "short explanation",
  "confidence": "high"
}
```

Python decides pass/fail:

```python
violations = (
    result["missing_requirements"]
    or result["forbidden_claims_found"]
    or result["unsupported_claims"]
)

passed = not bool(violations)
```

## Pilot Workflow

Use the pilot workflow when you want to test a more specific thesis:

> Are our meaningful failures actually caused by missing or misrouted context, and can reviewed knowledge reduce repeats?

### Step 1. Capture a suspicious run

Same as the normal workflow.

### Step 2. Run a pilot review

```bash
llmcheck pilot-review --latest
```

Current pilot taxonomy includes:

- `missing_context`
- `wrong_retrieval_target`
- `reasoning_failure_with_sufficient_context`
- `prompt_or_instruction_failure`
- `tool_or_workflow_failure`
- `policy_ambiguity`
- `acceptable_edge_case`
- `false_positive_detector`

Missing-context subtypes currently include:

- `missing_policy_fact`
- `missing_customer_state`
- `missing_workflow_rule`
- `missing_tool_result`
- `missing_document_section`
- `missing_disambiguation_context`

### Step 3. Approve a knowledge entry if justified

Knowledge types currently include:

- `policy_fact`
- `workflow_fact`
- `missing_context_to_fetch`
- `retrieval_hint`
- `canonical_correction`
- `known_failure_pattern`

The point is not to store arbitrary reviewer notes. The point is to keep typed, approved knowledge with explicit usage modes.

### Step 4. Inspect the scorecard

```bash
llmcheck pilot-scorecard
llmcheck pilot-report
llmcheck pilot-dashboard
```

The pilot is only meaningful if the scorecard tells you something uncomfortable or useful.

## Knowledge Entries And Retrieval Policy

This part needs precision.

LLMCheck does not currently implement a general semantic memory layer.

It currently implements a narrower, workflow-scoped reuse path for approved knowledge entries.

### How entries are matched

Current matching is:

1. filter approved entries by workflow scope
2. filter by required usage mode
3. token-match the user query against the entry title/body/scope fields
4. inject matching entries if applicable

This is a lightweight heuristic, not a full retrieval engine.

### Current usage modes

The code currently supports these usage modes:

- `detection_only`
- `review_assist_only`
- `retrieval_planning_only`
- `runtime_retrieval_allowed`

Current enforcement is intentionally conservative:

- `retrieval_planning_only` injects a system message with reviewed planning guidance
- `runtime_retrieval_allowed` injects a system message with approved runtime context
- `detection_only` and `review_assist_only` are stored, but not yet injected into model calls

### What later runs actually receive

If a matching entry is approved for injection, LLMCheck prepends one or more system messages before the original app messages.

Example shape:

```text
system: Reviewed retrieval-planning guidance for this workflow:
- Acme refund approval policy: Acme refunds above $137 require finance approval and take 9 business days.

system: Approved runtime context for this workflow:
- Acme refund approval policy: Acme refunds above $137 require finance approval and take 9 business days.
```

The run metadata also records which knowledge entries were applied.

### What this does not mean

It does not mean:

- the model now has a safe long-term memory
- every approved note should be injected later
- semantic retrieval is fully solved
- the system can generally "learn" from arbitrary feedback

The current implementation is deliberately smaller and more auditable than that.

## Example App

See [examples/rag_support_agent.py](/Users/nextwebb/Documents/llmcheck/examples/rag_support_agent.py:1).

It shows:

- OpenAI instrumentation
- a fake retriever
- `add_context(...)`
- `add_tags(...)`
- a captured completion call
- optional run flagging

## Typical Usage Patterns

### Pattern 1. Local dev regression loop

Use this when:

- you found a bad output
- you want to turn it into a replayable check quickly

Commands:

```bash
llmcheck list --flagged
llmcheck review --latest
llmcheck run-suite
```

### Pattern 2. Pilot one workflow before building more system

Use this when:

- you suspect missing context is a real issue
- you do not yet know if a memory layer is justified

Commands:

```bash
llmcheck pilot-review --latest
llmcheck pilot-scorecard
llmcheck pilot-report
llmcheck pilot-dashboard
```

### Pattern 3. App-level explicit storage path

Use this when your app process may not start in the right working directory.

```python
from pathlib import Path
from openai import OpenAI
from llmcheck import instrument_openai

client = instrument_openai(
    OpenAI(),
    storage_path=Path("/absolute/path/to/project/.llmcheck/llmcheck.db"),
)
```

This avoids ambiguous capture locations.

## Open Source Vs Hosted

The current repository is an open-source local core.

That makes sense because the hard product questions are still:

- which incident types are worth keeping?
- which reviewed knowledge is safe to reuse?
- how much of the failure pool is actually a missing-context problem?
- does the knowledge loop reduce repeats enough to matter?

If you later offer a hosted version, a useful split would be:

Open-source local core:

- instrumentation
- local storage
- review/export flows
- suite replay
- pilot dashboard

Possible hosted layer:

- team review queue
- shared dashboards
- org-level workflow analytics
- collaboration and audit surfaces
- usage-based pricing around team operations, not basic capture

That is a product direction, not a claim about what exists in this repo today.

## Limits

Current limitations matter more than aspirational features.

LLMCheck does not currently provide:

- Anthropic instrumentation
- Gemini instrumentation
- broad multi-provider capture
- hosted review queues
- auto-clustering of incidents
- production alerting
- general-purpose semantic memory
- proof that an answer is correct
- automatic elimination of hallucinations

Pilot-specific limits:

- the pilot dashboard only visualizes `pilot_reviews` and `knowledge_entries`
- runtime reuse is currently based on workflow scope plus lightweight token overlap
- only some usage modes are actually enforced during later runs
- one pilot success does not validate the broader business thesis

## Security And Privacy

LLMCheck is local-first by default.

That means:

- runs are stored locally in SQLite
- no LLMCheck-managed remote service is used
- API keys should come from your environment, not from `llmcheck.yaml`

Current judge behavior:

- regression replay may call OpenAI if you use the OpenAI judge
- the judge uses `OPENAI_API_KEY`
- LLMCheck does not store your secrets

If you are capturing sensitive production traffic, you still need to make your own decisions about:

- what user data enters the database
- what gets sent to the model provider
- whether redaction is needed before capture or replay

## Development And Tests

Run the test suite:

```bash
pytest -q
```

Current tests use mocks or fakes for provider calls by default. Live API use is not required for the main test suite.

## A Good First Evaluation

If you are deciding whether this tool is useful for your team, do not start by building more system surface.

Start with one workflow and answer these:

1. Are bad runs repeating in a recognizable shape?
2. Are those failures often caused by missing or misrouted context?
3. Can reviewers produce stable, typed knowledge quickly?
4. Does approved knowledge improve later runs or only add prompt noise?

If the answer to those is weak, keep the regression-check loop and be skeptical of the memory-heavy direction.
