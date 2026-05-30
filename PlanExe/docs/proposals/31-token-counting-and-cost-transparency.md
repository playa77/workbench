---
title: Token Counting + Cost Transparency (Raw Provider Tokens)
date: 2026-02-10
status: proposal
author: Larry the Laptop Lobster
---

# Token Counting + Cost Transparency (Raw Provider Tokens)

## Pitch
Expose per-plan token usage and cost breakdowns, using raw provider token counts to enable transparent budgeting, optimization, and governance.

## Why
Token costs are opaque and often underestimated. Transparent cost accounting is essential for budgeting, pricing, and scaling decisions.

## Problem

- Users cannot see cost drivers across steps.
- Internal teams cannot optimize prompt and model usage.
- Investors and operators lack visibility into plan-generation cost structure.

## Proposed Solution
Implement a token accounting layer that:

1. Captures raw provider token counts for every model call.
2. Maps tokens to cost using provider pricing tables.
3. Aggregates cost by plan stage, plugin, and model.
4. Surfaces a user-facing cost report.

## Data Model

### Token Event Schema

```json
{
  "plan_id": "plan_123",
  "stage": "assume",
  "model": "gpt-4o-mini",
  "input_tokens": 4200,
  "output_tokens": 900,
  "provider_cost_usd": 0.034
}
```

### Aggregation Schema

```json
{
  "plan_id": "plan_123",
  "total_cost_usd": 1.42,
  "by_stage": {
    "assume": 0.35,
    "risk": 0.22,
    "finance": 0.47
  },
  "by_model": {
    "gpt-4o-mini": 0.78,
    "gemini-2.0-flash": 0.64
  }
}
```

## Reporting Views

- **Plan Cost Summary:** total tokens, total cost, top cost drivers.
- **Stage Breakdown:** cost per pipeline stage.
- **Model Breakdown:** cost per model/provider.
- **Optimization Insights:** suggestions to reduce high-cost stages.

## Governance Features

- Cost caps per plan or per day.
- Alerts when costs exceed thresholds.
- Audit logs for cost anomalies.

## Integration Points

- Works with all pipeline stages and plugins.
- Feeds budgeting dashboards.
- Used in governance and allocation decisions.

## Success Metrics

- Cost visibility for 100% of plans.
- Reduction in cost per plan after optimization.
- Fewer cost overruns and unexpected bills.

## Risks

- Provider token counts may change or be inconsistent.
- Cost reporting overhead adds latency.
- Misinterpretation of cost data by users.

## Future Enhancements

- Per-user or per-team cost budgeting.
- Predictive cost estimation before plan generation.
- Multi-currency cost reporting.

## Detailed Implementation Plan

### 1) Instrumentation in `llm.py` (source of truth)

Implement a provider-normalization layer around every outbound model call:

1. Capture request metadata before call:
   - `run_id`, `stage`, `provider`, `model`, `prompt_variant`, `started_at`
2. Execute provider call unchanged.
3. Read **raw provider response** and parse usage fields:
   - OpenAI-style: `usage.prompt_tokens`, `usage.completion_tokens`, reasoning fields when present
   - Anthropic-style: `input_tokens`, `output_tokens`, thinking-token fields when present
   - Gemini/OpenRouter: normalized usage from provider envelope
4. Persist raw usage payload JSON for audit (`raw_usage_json`) plus normalized fields.

### 2) Token schema and persistence

Create a DB table such as:

```sql
CREATE TABLE llm_call_usage (
  id UUID PRIMARY KEY,
  run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INT,
  output_tokens INT,
  reasoning_tokens INT,
  cached_tokens INT,
  cost_usd NUMERIC(12,6),
  latency_ms INT,
  raw_usage_json JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

And a summary view/table:

```sql
CREATE MATERIALIZED VIEW llm_run_usage_summary AS
SELECT run_id,
       SUM(input_tokens) AS input_tokens,
       SUM(output_tokens) AS output_tokens,
       SUM(reasoning_tokens) AS reasoning_tokens,
       SUM(cost_usd) AS total_cost_usd,
       COUNT(*) AS call_count
FROM llm_call_usage
GROUP BY run_id;
```

### 3) Cost engine

Add a `pricing_catalog` keyed by provider+model with time-versioned rates:
- input per 1k tokens
- output per 1k tokens
- reasoning per 1k tokens (if billed separately)

Cost formula per call:

`cost = (input_tokens/1000)*rate_in + (output_tokens/1000)*rate_out + (reasoning_tokens/1000)*rate_reason`

Store calculated cost and the `pricing_version` used for reproducibility.

### 4) API/report integration

- Extend run status endpoint with:
  - total tokens and cost
  - stage-by-stage usage table
  - model/provider breakdown
- Add a report section in generated plan artifacts:
  - “Cost & Token Accounting”
  - includes confidence note when provider usage is partially missing.

### 5) Structured output handling rule

Critical implementation detail:
- Usage is captured from provider raw envelope **before** JSON parsing/validation.
- Structured-output parse failures should not lose token accounting.

### 6) Reliability and edge cases

- If provider usage fields missing:
  - mark `usage_quality = estimated`
  - optional fallback tokenizer estimate
- For retries:
  - log each retry as independent call record
  - include `attempt_number`
- For streaming:
  - aggregate chunk usage if available; else finalize from closing usage frame.

### 7) Rollout phases

- Phase A: capture + store usage only (no UI)
- Phase B: cost engine + summary endpoint
- Phase C: user-visible report + budget alerts
- Phase D: optimization recommendations (cost hot spots)

### 8) Validation checklist

- Unit tests for provider mapping parsers
- Golden tests with canned raw provider responses
- Billing reconciliation tests against provider invoices
- Backfill script for historical runs where data exists

## Detailed Implementation Plan (Operational Rollout)

### Deployment Path
1. Ship instrumentation behind `TOKEN_ACCOUNTING_ENABLED` feature flag.
2. Enable in staging first; reconcile with provider dashboards for 1 week.
3. Roll out to production with alerting on missing usage payloads.

### Cost Reconciliation Workflow
- Daily batch compares internal aggregated cost to provider invoice API.
- If variance >2%, emit finance alert and lock optimization recommendations until corrected.

### Observability
- Metrics: `token_usage_capture_rate`, `usage_parse_failures`, `cost_variance_pct`.
- Dashboards by provider/model/stage.

### Ownership Model
- Platform team owns parser + pricing catalog.
- Product team owns user-facing reports and budget controls.

