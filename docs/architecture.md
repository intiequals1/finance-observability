# Architecture Overview

Finance Observability is organized around four layers: sources, ingestion, finance rules, and observability.

## 1. Sources

Supported and planned source types:

- SEC EDGAR / XBRL public company facts
- CSV and Excel files
- REST APIs
- SAP FI/CO and S/4HANA demo extracts

All examples should use public, synthetic, or anonymized data.

## 2. Ingestion

The ingestion layer extracts source data, normalizes it into a common finance observation model, and stores it in PostgreSQL.

Typical responsibilities:

- Source-specific extraction
- Field normalization
- Type conversion
- Load metadata
- Error capture
- Idempotent loading where possible

## 3. Finance Rule Engine

The finance rule engine evaluates data quality and control rules.

Rule categories:

- Freshness
- Completeness
- Consistency
- Plausibility
- Reconciliation
- Materiality

Rules should be deterministic, documented, and testable.

## 4. Observability

Observability turns finance control results into operational signals.

Signals include:

- Prometheus metrics
- Structured logs
- OpenTelemetry traces
- Grafana dashboards
- Alert rules

## Design goals

- Separate extraction from validation
- Keep rules independent from visualization
- Make assumptions visible
- Prefer open standards and public data
- Treat finance data quality as a first-class operational concern
