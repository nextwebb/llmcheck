# Security and privacy

LLMCheck can store prompts, outputs, context and metadata in plain local SQLite and YAML files. It does not provide encryption at rest, tenant isolation or automatic redaction. Retain only data you are authorized to store and protect the workspace with your operating system's access controls.

The default semantic judge sends case material and application output to OpenAI. Local storage does not mean every operation is offline. Your application callable can contact other services, write files or perform real actions. Inspect suites and adapters before executing them; use controlled test environments.

The public synthetic demo is separate from the workspace dashboard. Do not expose a private pilot dashboard to the public internet or serve a real workspace database as demonstration data. A read-only interface still requires deliberate selection of the data it displays.

Never include credentials in prompts, context, test fixtures, screenshots or reports. Keep API keys in your secret-management system. Rotate any credential accidentally disclosed.

## Reporting a vulnerability

No dedicated private security contact or response-time commitment has been established. If GitHub's private vulnerability reporting option is available on the repository, use it. Otherwise contact the maintainer privately before sharing exploit details; do not post sensitive payloads or application data in a public issue. This document does not assert that private reporting is currently enabled.

The project is a release candidate. No supported-version security maintenance window or production-security certification is claimed.
