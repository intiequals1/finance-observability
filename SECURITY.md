# Security Policy

## Supported versions

This project is in an early development phase. Security fixes will target the default branch until versioned releases are introduced.

## Reporting a vulnerability

Please do not disclose security vulnerabilities publicly before they are reviewed.

Open a private security advisory on GitHub if available, or contact the repository maintainer through the channels listed on the GitHub profile.

## Secrets and data handling

- Never commit `.env` files.
- Never commit API keys, tokens, passwords, or private keys.
- Never commit customer financial data, production ledger extracts, or confidential ERP exports.
- Use public, synthetic, or anonymized data for examples and tests.

## Scope

This project is intended for observability and data quality experimentation. It is not financial advice, audit certification, or a replacement for internal controls.
