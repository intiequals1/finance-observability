# Contributing

Thank you for your interest in Finance Observability.

## Principles

- Use public, synthetic, or anonymized data only.
- Do not commit secrets, credentials, API keys, tokens, or private financial data.
- Keep finance rules readable and testable.
- Prefer small, focused pull requests.
- Document assumptions and limitations.

## Development workflow

1. Open or pick an issue.
2. Create a feature branch.
3. Add or update tests where practical.
4. Run local checks before opening a pull request.
5. Open a pull request with a clear description of the change.

## Branch naming

Use descriptive names:

```text
feature/sec-ingestion
feature/finance-rules
fix/grafana-query
chore/project-structure
```

## Commit style

Use concise conventional-style messages:

```text
docs: update architecture overview
feat: add SEC ingestion client
fix: handle missing facts safely
chore: add CI workflow
```

## Data policy

This repository should not contain customer data, production ledgers, private ERP extracts, or confidential filings. Demo data must be public or synthetic.
