# 0.4.0 release validation

Validation date: 23 September 2026. This is a small local developer tool plus a finite public demonstration, not a hosted multi-user evaluation service.

## Fixed since the article's 0.3.0 baseline

- Draft generation no longer interprets quotation marks as forbidden claims. The correction remains in the rubric; reviewers explicitly author phrase lists.
- Empty suites and asynchronous runner outputs raise actionable errors rather than produce misleading results.
- Invalid judge fields, malformed provider envelopes and timeouts use typed error paths.
- Pending capture context and tags are consumed per attempt. Failed calls cannot contaminate later captures or leave a stale flag target.
- Failure to persist a successful completion warns without replacing the provider response with an application exception.
- Stored dashboard text is escaped before HTML interpolation. HEAD responses have no body.
- Wheel installation is independent of the original checkout. Source distributions can rebuild away from the source directory.
- The complete local state directory and environment files are excluded from version control and distributions.

## Live evaluation

The bounded script made 12 sequential requests with no retries to `gpt-4o-mini-2024-07-18` using synthetic refund-policy fixtures. All requests completed. Results: 5 true positives, 6 true negatives, 0 false positives, 1 false negative. Positive means policy compliant / PASS.

The rejected compliant case said “Do not expect an instant refund.” The judge treated the negated phrase as a forbidden claim. This failure is preserved; the prompt was not tuned and rerun to hide it. These selected cases are not representative accuracy, a calibration study, or evidence of production reliability. Token usage is unavailable through the existing content-only transport, not zero. No latency or cost measurements are claimed.

The evidence records the baseline Git commit plus the exact judge and evaluation-script SHA256 hashes. The run used an uncommitted 0.4.0 candidate, so the baseline commit alone does not identify all evaluated bytes. Inspect hashes when reproducing. Public demo OpenAI mode displays recorded results; clicks do not spend API credits.

## Deployment boundary

The Render demo uses only bundled synthetic fixtures and recorded evaluation evidence. No provider key is deployed. It accepts no visitor prompts, database uploads or arbitrary runner code. Core APIs execute a fixed local fixture suite; results are cached after startup. Render free storage is ephemeral and services may sleep. Persistent capture belongs to the installed local product.

The article companion download reproduces the original 0.3.0 article; its README pins that revision. This preserves the historical defect reproduction while 0.4.0 repairs it. No claim that the old defect persists in the new release is warranted.

## Not established

Broad provider support, streaming capture, multi-user hosting, semantic memory quality, confidence calibration, independent human benchmarking and production suitability remain outside the release claim. The core is licensed under Apache-2.0; this does not imply a published PyPI package or completion of the prospective SaaS product.

## Deployment verification

The free Render service at https://llmcheck-demo.onrender.com deployed commit `ce91167` successfully. Public `/healthz` returned version `0.4.0`; the downloaded companion SHA256 matched the bundled archive (`fb9eacc29b4a265fa5c995a189f5bf4324a24d35f352ecbcdc8748299c8f6b56`). Browser verification confirmed recorded-mode case selection and the preserved negation false failure. The local suite passed 53 tests. These checks verify the stated paths, not general production readiness.
