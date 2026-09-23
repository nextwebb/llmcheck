# Article examples

Browsable source for the article's offline capture/review/replay demonstration and historical experiments. No separate ZIP, API key or live provider call is needed. All policies and responses are synthetic, and the injected literal judge is a test double, not an evaluation of the default semantic judge.

## Reproduce the article

Use Python 3.10 or later, Git and PyYAML. Clone `main` for these example files, then create a separate historical worktree for the library code used by the article. The historical commit does **not** contain this examples directory; keep running the scripts from the `main` checkout and pass the historical checkout with `--repo`.

```sh
git clone --branch main https://github.com/nextwebb/llmcheck.git
cd llmcheck
python3 -m venv .venv
. .venv/bin/activate
python -m pip install PyYAML

git worktree add --detach ../llmcheck-article-reference 6d101ae90781b8dc06965f57313445f8878cf6d6
ARTICLE_REPO="$(cd ../llmcheck-article-reference && pwd)"
ARTICLE_OUTPUT="$(mktemp -d)"

python examples/article/offline_demo.py --repo "$ARTICLE_REPO" --output "$ARTICLE_OUTPUT/demo"
python examples/article/smoke_test.py --repo "$ARTICLE_REPO"
python examples/article/inspect_results.py "$ARTICLE_OUTPUT/demo/replay-results.json"
```

The demo writes captured data, the original generated draft, the explicitly reviewed case, replay results and source provenance into the new output directory. It refuses to overwrite a nonempty directory. Expected replay verdicts are **FAIL, PASS, FAIL, FAIL**. The inspector reads stored results without rerunning the application or judge. The smoke test uses its own temporary directory and checks capture, review, all four outcomes and overwrite protection.

## Reproduce the historical experiments

The original experiment scripts write beside themselves. Copy the evidence directory into the temporary output folder before running them, so generated records remain separate from the checked-in reference fixtures:

```sh
cp -R examples/article/evidence "$ARTICLE_OUTPUT/evidence"
LLMCHECK_REPO="$ARTICLE_REPO" python "$ARTICLE_OUTPUT/evidence/twelve-cases/run.py"
LLMCHECK_REPO="$ARTICLE_REPO" python "$ARTICLE_OUTPUT/evidence/gate-probes/run.py"
```

- [Twelve-case experiment](evidence/twelve-cases/run.py): twelve deliberately selected cases produce four agreements and eight disagreements against hand-authored policy expectations (two true positives, two true negatives, four false positives and four false negatives). These counts describe the injected substring judge, not real-world accuracy. See the [case fixtures](evidence/twelve-cases/cases.json) and [reference CSV](evidence/twelve-cases/results.csv).
- [Gate and draft probes](evidence/gate-probes/run.py): verify historical gate behavior and a historical draft-generation defect. Empty violation arrays pass at both high and low confidence, a reported violation fails, malformed JSON errors, and the old generated draft puts a quoted required phrase in the forbidden list.

The scripts preserve the historical experiment logic. Use the pinned library commit above for the article figures and draft probe: current versions corrected draft generation, so the historical draft assertions are intentionally not current-version tests. Generated provenance records the checkout commit. Runtime IDs, timestamps and absolute paths can differ between runs.

## Try the current library

The offline demo and smoke test also pass against the `main` checkout used to publish these examples:

```sh
python examples/article/offline_demo.py --repo . --output "$ARTICLE_OUTPUT/current-demo"
python examples/article/smoke_test.py --repo .
```

This checks the current capture/review/replay workflow; it does not recreate the old generated draft. The [interactive explorer](https://llmcheck-demo.onrender.com/#explorer) provides a browser view of the twelve cases. Its recorded live evaluation is separate from these offline experiments.
