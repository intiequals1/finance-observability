-- Finance Observability — PostgreSQL schema
-- Auto-executed by postgres container on first start via docker-entrypoint-initdb.d

CREATE TABLE IF NOT EXISTS company_facts (
  id           BIGSERIAL PRIMARY KEY,
  loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  ticker       TEXT        NOT NULL,
  cik          TEXT        NOT NULL,
  fiscal_year  INT         NOT NULL,
  fiscal_period TEXT       NOT NULL,
  form         TEXT        NOT NULL,
  filed_at     DATE,
  concept      TEXT        NOT NULL,
  value        NUMERIC,
  unit         TEXT,
  frame        TEXT,
  UNIQUE (ticker, fiscal_year, fiscal_period, form, concept, unit)
);

CREATE TABLE IF NOT EXISTS dq_results (
  id          BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  ticker      TEXT        NOT NULL,
  check_name  TEXT        NOT NULL,
  severity    TEXT        NOT NULL,  -- critical | high | medium | low
  status      TEXT        NOT NULL,  -- PASS | WARN | FAIL
  details     TEXT
);

CREATE INDEX IF NOT EXISTS idx_company_facts_ticker_year
  ON company_facts (ticker, fiscal_year DESC);

CREATE INDEX IF NOT EXISTS idx_dq_results_ticker_created
  ON dq_results (ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dq_results_status
  ON dq_results (status) WHERE status IN ('FAIL', 'WARN');
