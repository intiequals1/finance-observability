import os
import time
import threading
from datetime import datetime, timezone, date
from decimal import Decimal

import psycopg2
import requests
import uvicorn
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://finance:finance@localhost:5432/finance")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "finance-observability-mvp contact@example.com")
COMPANIES = [c.strip().upper() for c in os.getenv("COMPANIES", "AAPL,MSFT,AMZN").split(",") if c.strip()]
LOAD_INTERVAL_SECONDS = int(os.getenv("LOAD_INTERVAL_SECONDS", "3600"))

# Freshness threshold: 18 calendar months = 548 days
FRESHNESS_THRESHOLD_DAYS = 548

TICKER_CIK = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
    "META": "0001326801",
    "TSLA": "0001318605",
    "NVDA": "0001045810",
}

CONCEPTS = {
    "Assets": ["Assets"],
    "Liabilities": ["Liabilities"],
    "Equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "Revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "NetIncome": ["NetIncomeLoss"],
    "Cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
}

LOAD_SUCCESS = Counter("finance_etl_load_success_total", "Successful ETL loads")
LOAD_FAILURE = Counter("finance_etl_load_failure_total", "Failed ETL loads")
DQ_FAILURES = Gauge("finance_dq_failures", "Current finance DQ failures")
DQ_WARNINGS = Gauge("finance_dq_warnings", "Current finance DQ warnings")
LOAD_LATENCY = Histogram("finance_etl_load_latency_seconds", "ETL load latency")
FACT_ROWS = Gauge("finance_fact_rows", "Rows in company_facts")
FRESHNESS_DAYS = Gauge("finance_data_freshness_days", "Days since latest filed date", ["ticker"])

app = FastAPI(title="Finance Observability")


def db():
    return psycopg2.connect(DATABASE_URL)


def upsert_fact(cur, ticker, cik, fy, fp, form, filed, concept, value, unit, frame):
    cur.execute(
        """
        INSERT INTO company_facts
        (ticker, cik, fiscal_year, fiscal_period, form, filed_at, concept, value, unit, frame)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker, fiscal_year, fiscal_period, form, concept, unit)
        DO UPDATE SET
            loaded_at = now(),
            filed_at = EXCLUDED.filed_at,
            value = EXCLUDED.value,
            frame = EXCLUDED.frame
        """,
        (ticker, cik, fy, fp, form, filed, concept, value, unit, frame),
    )


def sec_companyfacts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(
        url,
        headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def extract_sec_facts(ticker):
    cik = TICKER_CIK.get(ticker)
    if not cik:
        return []
    data = sec_companyfacts(cik)
    facts = data.get("facts", {}).get("us-gaap", {})
    rows = []
    for canonical, variants in CONCEPTS.items():
        found = None
        for concept in variants:
            if concept in facts:
                found = concept
                break
        if not found:
            continue
        units = facts[found].get("units", {})
        for unit, entries in units.items():
            for e in entries:
                if e.get("form") not in {"10-K", "10-Q"}:
                    continue
                if not e.get("fy") or not e.get("fp") or e.get("val") is None:
                    continue
                rows.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "fy": int(e["fy"]),
                        "fp": e["fp"],
                        "form": e["form"],
                        # FIX: sort by filed date before trimming so we get the latest 500
                        "filed": e.get("filed"),
                        "concept": canonical,
                        "value": Decimal(str(e["val"])),
                        "unit": unit,
                        "frame": e.get("frame"),
                    }
                )
    # FIX: sort by filed date descending, then take latest 500
    rows.sort(key=lambda r: r["filed"] or "", reverse=True)
    return rows[:500]


def insert_sample_data(cur):
    sample = [
        ("AAPL", "0000320193", 2023, "FY", "10-K", "2023-11-03", "Assets", 352583000000, "USD", "CY2023"),
        ("AAPL", "0000320193", 2023, "FY", "10-K", "2023-11-03", "Liabilities", 290437000000, "USD", "CY2023"),
        ("AAPL", "0000320193", 2023, "FY", "10-K", "2023-11-03", "Equity", 62146000000, "USD", "CY2023"),
        ("AAPL", "0000320193", 2023, "FY", "10-K", "2023-11-03", "Revenue", 383285000000, "USD", "CY2023"),
        ("MSFT", "0000789019", 2023, "FY", "10-K", "2023-07-27", "Assets", 411976000000, "USD", "CY2023"),
        ("MSFT", "0000789019", 2023, "FY", "10-K", "2023-07-27", "Liabilities", 205753000000, "USD", "CY2023"),
        ("MSFT", "0000789019", 2023, "FY", "10-K", "2023-07-27", "Equity", 206223000000, "USD", "CY2023"),
        ("MSFT", "0000789019", 2023, "FY", "10-K", "2023-07-27", "Revenue", 211915000000, "USD", "CY2023"),
    ]
    for row in sample:
        upsert_fact(cur, *row)


def run_dq(cur):
    # Purge DQ results older than 7 days
    cur.execute("DELETE FROM dq_results WHERE created_at < now() - interval '7 days'")

    cur.execute("SELECT DISTINCT ticker FROM company_facts")
    tickers = [r[0] for r in cur.fetchall()]
    failures = 0
    warnings = 0

    for ticker in tickers:
        checks = []

        # --- Check 1: minimum fact rows ---
        cur.execute("SELECT count(*) FROM company_facts WHERE ticker = %s", (ticker,))
        row_count = cur.fetchone()[0]
        checks.append(
            ("minimum_fact_rows", "high", "PASS" if row_count >= 4 else "FAIL", f"rows={row_count}")
        )

        # --- Check 2: data freshness (threshold: 18 months = 548 days) ---
        cur.execute("SELECT max(filed_at) FROM company_facts WHERE ticker = %s", (ticker,))
        latest_filed = cur.fetchone()[0]
        if latest_filed:
            today = date.today()
            age_days = (today - latest_filed).days
            FRESHNESS_DAYS.labels(ticker=ticker).set(age_days)
            status = "WARN" if age_days > FRESHNESS_THRESHOLD_DAYS else "PASS"
            checks.append(
                (
                    "freshness_max_18_months",
                    "medium",
                    status,
                    f"latest_filed={latest_filed}, age_days={age_days}, threshold={FRESHNESS_THRESHOLD_DAYS}",
                )
            )
        else:
            checks.append(("freshness_max_18_months", "medium", "FAIL", "no filed_at found"))

        # --- Check 3: null values ---
        cur.execute(
            "SELECT count(*) FROM company_facts WHERE ticker = %s AND value IS NULL", (ticker,)
        )
        nulls = cur.fetchone()[0]
        checks.append(
            ("value_not_null", "critical", "PASS" if nulls == 0 else "FAIL", f"nulls={nulls}")
        )

        # --- Check 4: accounting equation (Assets = Liabilities + Equity) ---
        # FIX: explicitly detect missing concepts rather than silently downgrading to WARN
        cur.execute(
            """
            WITH latest AS (
                SELECT fiscal_year, fiscal_period, form
                FROM company_facts
                WHERE ticker = %s AND concept = 'Assets'
                ORDER BY fiscal_year DESC, filed_at DESC
                LIMIT 1
            ), pivot AS (
                SELECT
                    concept,
                    max(value) AS value
                FROM company_facts f
                JOIN latest l USING (fiscal_year, fiscal_period, form)
                WHERE f.ticker = %s AND concept IN ('Assets', 'Liabilities', 'Equity')
                GROUP BY concept
            )
            SELECT
                max(value) FILTER (WHERE concept = 'Assets')      AS assets,
                max(value) FILTER (WHERE concept = 'Liabilities') AS liabilities,
                max(value) FILTER (WHERE concept = 'Equity')      AS equity
            FROM pivot
            """,
            (ticker, ticker),
        )
        assets, liabilities, equity = cur.fetchone()

        if assets is not None and liabilities is not None and equity is not None:
            diff = abs(Decimal(str(assets)) - Decimal(str(liabilities)) - Decimal(str(equity)))
            tolerance = max(Decimal("1000000"), abs(Decimal(str(assets))) * Decimal("0.005"))
            status = "PASS" if diff <= tolerance else "FAIL"
            checks.append(
                (
                    "accounting_equation",
                    "critical",
                    status,
                    f"assets-liabilities-equity={diff}, tolerance={tolerance}",
                )
            )
        else:
            # FIX: missing concept is a DQ FAIL, not a generic WARN
            missing = [
                c
                for c, v in [("Assets", assets), ("Liabilities", liabilities), ("Equity", equity)]
                if v is None
            ]
            checks.append(
                (
                    "accounting_equation",
                    "critical",
                    "FAIL",
                    f"missing concepts for latest period: {', '.join(missing)}",
                )
            )

        # Write checks to DB
        for check_name, severity, status, details in checks:
            if status == "FAIL":
                failures += 1
            if status == "WARN":
                warnings += 1
            cur.execute(
                """
                INSERT INTO dq_results (ticker, check_name, severity, status, details)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (ticker, check_name, severity, status, details),
            )

    DQ_FAILURES.set(failures)
    DQ_WARNINGS.set(warnings)


def load_once():
    start = time.time()
    try:
        with db() as conn:
            with conn.cursor() as cur:
                loaded = 0
                for ticker in COMPANIES:
                    try:
                        rows = extract_sec_facts(ticker)
                    except Exception as exc:
                        print(f"[ETL] SEC load failed for {ticker}: {exc}", flush=True)
                        rows = []
                    for r in rows:
                        upsert_fact(
                            cur,
                            r["ticker"], r["cik"], r["fy"], r["fp"],
                            r["form"], r["filed"], r["concept"],
                            r["value"], r["unit"], r["frame"],
                        )
                        loaded += 1
                if loaded == 0:
                    print("[ETL] No live data loaded; inserting sample data", flush=True)
                    insert_sample_data(cur)
                run_dq(cur)
                cur.execute("SELECT count(*) FROM company_facts")
                FACT_ROWS.set(cur.fetchone()[0])
        LOAD_SUCCESS.inc()
        print(f"[ETL] Load complete — {loaded} rows, latency {time.time()-start:.1f}s", flush=True)
    except Exception as exc:
        LOAD_FAILURE.inc()
        print(f"[ETL] Load failed: {exc}", flush=True)
    finally:
        LOAD_LATENCY.observe(time.time() - start)


def loop():
    while True:
        load_once()
        time.sleep(LOAD_INTERVAL_SECONDS)


@app.get("/")
def root():
    return {"status": "ok", "companies": COMPANIES}


@app.post("/load")
def trigger_load():
    threading.Thread(target=load_once, daemon=True).start()
    return {"status": "load triggered"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
