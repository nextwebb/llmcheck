# Changelog

## 0.4.0 — unreleased candidate

- Generate conservative review drafts: preserve free-form correction in the rubric and leave required/forbidden lists for the reviewer.
- Reject empty suites and asynchronous application outputs; report malformed provider/confidence payloads as evaluation errors.
- Bound default judge completion requests to 512 tokens.
- Build portable wheels containing package files instead of checkout-dependent editable stubs.
- Add source-distribution builds and packaging checks for installation away from the source checkout.
- Include the README and source URL in distribution metadata; read the version from pyproject.toml.
- Replace the long README with installation, capture/review/replay and synthetic-demo guidance; move detailed reference material into docs/reference.md.
- Add contributing and security guidance. Licensing remains an explicit release decision.

The candidate is not a claim of a PyPI publication, a verified hosted demo URL or production adoption. Other feature changes must be verified against the final release diff before tagging.

## 0.3.0

Existing local capture, review, replay and experimental knowledge-workflow baseline. Earlier release publication dates are not reconstructed here.
