# Autonomous decision records

The OMP manager stores evidence-backed decisions made by the delegated
multi-model quorum here. These records are an audit trail for unattended work;
they do not replace accepted decisions in `../medcore-docs` or the backend
architecture documents.

Use one Markdown file per material decision:

```text
YYYY-MM-DD-<feature>-<short-slug>.md
```

Do not store credentials, JWTs, cookies, Telegram secrets, or raw sensitive
payloads. Link to source paths and line numbers instead.
