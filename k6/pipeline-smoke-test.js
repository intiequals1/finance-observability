/**
 * k6 smoke test for finance-observability ETL pipeline
 *
 * Tests:
 *   - /health endpoint availability
 *   - /metrics endpoint returns Prometheus text format
 *   - POST /load triggers successfully and completes within threshold
 *   - Key Prometheus metrics are present after a load
 *
 * Usage:
 *   k6 run k6/pipeline-smoke-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';

const BASE_URL = __ENV.ETL_URL || 'http://localhost:8000';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<10000'],  // load endpoint may take several seconds
    checks: ['rate==1.0'],               // all checks must pass
  },
};

export default function () {
  group('health check', () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, {
      'health status 200': (r) => r.status === 200,
      'health returns ok': (r) => {
        try { return JSON.parse(r.body).status === 'healthy'; } catch { return false; }
      },
    });
  });

  sleep(0.5);

  group('metrics endpoint', () => {
    const res = http.get(`${BASE_URL}/metrics`);
    check(res, {
      'metrics status 200': (r) => r.status === 200,
      'metrics content-type is prometheus': (r) =>
        (r.headers['Content-Type'] || '').includes('text/plain'),
      'finance_etl_load_success_total present': (r) =>
        r.body.includes('finance_etl_load_success_total'),
      'finance_dq_failures present': (r) =>
        r.body.includes('finance_dq_failures'),
    });
  });

  sleep(0.5);

  group('trigger load and verify', () => {
    // Trigger a synchronous load
    const loadRes = http.post(`${BASE_URL}/load`, null, { timeout: '30s' });
    check(loadRes, {
      'load trigger status 200': (r) => r.status === 200,
    });

    sleep(2);  // allow metrics to update

    // Verify metrics reflect a completed load
    const metricsRes = http.get(`${BASE_URL}/metrics`);
    check(metricsRes, {
      'fact_rows gauge is set': (r) => {
        const match = r.body.match(/finance_fact_rows\s+([\d.]+)/);
        return match && parseFloat(match[1]) > 0;
      },
      'load_success counter incremented': (r) => {
        const match = r.body.match(/finance_etl_load_success_total\s+([\d.]+)/);
        return match && parseFloat(match[1]) >= 1;
      },
    });
  });
}
