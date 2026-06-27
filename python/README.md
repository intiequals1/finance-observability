# Python Modules

This directory contains the Python implementation for Finance Observability.

## Planned modules

- `ingestion/` - source connectors and loaders
- `validation/` - finance data quality rules
- `reconciliation/` - source-to-target reconciliation logic
- `anomaly_detection/` - anomaly scoring and explanations
- `reporting/` - report and metric generation
- `api/` - service endpoints and health checks

The code should remain modular so data sources can be added without changing the validation and observability layers.
