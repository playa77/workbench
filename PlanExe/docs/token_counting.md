---
title: Token counting implementation
---

# Token counting implementation

This document describes the token counting feature that tracks LLM usage for each task execution. It includes architecture, API usage, migration behavior, and implementation status.

---

## Implementation summary

Token counting and per-call metrics are implemented and integrated into plan execution.

### Files added

- `database_api/model_token_metrics.py`
- `worker_plan/worker_plan_internal/llm_util/token_counter.py`
- `worker_plan/worker_plan_internal/llm_util/token_metrics_store.py`
- `worker_plan/worker_plan_internal/llm_util/token_instrumentation.py`
- `docs/token_counting.md`

### Files updated

- `worker_plan/app.py`
- `frontend_multi_user/src/app.py`
- `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py`

### Features delivered

- Automatic token tracking across LLM calls
- Aggregated and detailed task-level metrics endpoints
- Database-backed persistence with indexed queries
- Graceful degradation when database access is unavailable
- Provider-aware extraction for OpenAI-compatible, Anthropic, and LLamaIndex response shapes
- Routed-provider visibility (`upstream_provider`, `upstream_model`)
- Per-call USD cost when provider reports usage cost
- User attribution (`user_id`) for billing/support investigations

---

## Overview

The token counting system captures and stores metrics from LLM calls made during plan execution, including:

- **Input tokens**: Tokens in prompt/query content
- **Output tokens**: Tokens in model responses
- **Thinking tokens**: Reasoning/internal tokens (when provided by provider)
- **Cost USD**: Per-call provider cost (when provided by provider usage payload)
- **Call duration**: Time per invocation
- **Success/failure**: Call outcome and optional error message
- **Routed provider/model**: Upstream provider route for gateway backends (for example OpenRouter routing)
- **User attribution**: `user_id` for operator support and payment triage
  - Current runtime behavior:
    - Local admin flow may emit `user_id = "admin"`
    - OAuth/MCP flows emit `user_id = <uuid>`

---

## Architecture

### Components

1. **Database model** (`database_api/model_token_metrics.py`)
   - `TokenMetrics`: Stores per-call metrics
   - `TokenMetricsSummary`: Aggregated task statistics

2. **Token extraction** (`worker_plan/worker_plan_internal/llm_util/token_counter.py`)
   - `TokenCount`: Container object for parsed counts
   - `extract_token_count()`: Handles common response formats

3. **Metrics storage** (`worker_plan/worker_plan_internal/llm_util/token_metrics_store.py`)
   - `TokenMetricsStore`: Record, list, and summarize metrics
   - Lazy database loading to reduce import coupling

4. **Pipeline integration** (`worker_plan/worker_plan_internal/llm_util/token_instrumentation.py`)
   - `set_current_task_id()`
   - `set_current_user_id()`
   - `record_llm_tokens()`
   - `record_attempt_tokens()`

5. **Event-level usage source** (`worker_plan/worker_plan_internal/llm_util/track_activity.py`)
   - Captures `LLM*EndEvent` payloads where provider usage metadata is available
   - Persists token/cost/provider rows from event payloads
   - Computes duration by correlating `LLM*StartEvent` and `LLM*EndEvent`

6. **API endpoints** (`worker_plan/app.py`)
   - `GET /token-metrics/{task_id}`
   - `GET /token-metrics/{task_id}/detailed`

---

## Database schema

### `token_metrics`

```sql
CREATE TABLE token_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    llm_model VARCHAR(255) NOT NULL,
    task_id VARCHAR(255),
    user_id VARCHAR(255),
    upstream_provider VARCHAR(255),
    upstream_model VARCHAR(255),
    input_tokens INTEGER,
    output_tokens INTEGER,
    thinking_tokens INTEGER,
    cost_usd FLOAT,
    duration_seconds FLOAT,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    raw_usage_data JSON,
    INDEX idx_llm_model (llm_model),
    INDEX idx_task_id (task_id),
    INDEX idx_user_id (user_id),
    INDEX idx_timestamp (timestamp)
);
```

---

## Migration behavior

For existing installations, schema normalization runs automatically on startup in worker and frontend services.

Normalization rules:

- Ensure `task_id`, `user_id`, `upstream_provider`, `upstream_model`, and `cost_usd` exist
- Drop legacy `run_id` and `task_name` columns if present

This avoids runtime mismatches where old schemas block new writes.

If needed:

```python
from database_api.planexe_db_singleton import db
from database_api.model_token_metrics import TokenMetrics

db.create_all()
```

---

## API usage

### Aggregated metrics

```bash
curl http://localhost:8000/token-metrics/de305d54-75b4-431b-adb2-eb6b9e546014
```

Example response:

```json
{
  "task_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
  "total_input_tokens": 45231,
  "total_output_tokens": 12450,
  "total_thinking_tokens": 0,
  "total_tokens": 57681,
  "total_duration_seconds": 234.5,
  "total_calls": 42,
  "successful_calls": 41,
  "failed_calls": 1,
  "metrics": []
}
```

### Detailed metrics

```bash
curl http://localhost:8000/token-metrics/de305d54-75b4-431b-adb2-eb6b9e546014/detailed
```

Example response:

```json
{
  "task_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
  "count": 42,
  "metrics": [
    {
      "id": 1,
      "timestamp": "1984-02-10T12:00:15.123456",
      "llm_model": "gpt-4-turbo",
      "task_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
      "user_id": "admin",
      "upstream_provider": "Google",
      "upstream_model": "google/gemini-2.0-flash-001",
      "input_tokens": 1234,
      "output_tokens": 567,
      "thinking_tokens": 0,
      "total_tokens": 1801,
      "cost_usd": 0.001,
      "duration_seconds": 5.2,
      "success": true,
      "error_message": null
    }
  ]
}
```

---

## Provider support

Supported targets include:

- OpenAI-compatible providers (OpenAI, OpenRouter, Groq, custom endpoints)
- Anthropic responses (including cache-related usage fields)
- Ollama and LM Studio through compatible response structures
- LLamaIndex `ChatResponse` wrappers

The extractor accepts partial usage payloads and records `None` where fields are missing.

---

## Manual instrumentation

```python
from worker_plan_internal.llm_util.token_instrumentation import set_current_task_id
from worker_plan_internal.llm_util.token_instrumentation import set_current_user_id
from worker_plan_internal.llm_util.token_metrics_store import get_token_metrics_store

set_current_task_id("de305d54-75b4-431b-adb2-eb6b9e546014")
set_current_user_id("admin")

store = get_token_metrics_store()
store.record_token_usage(
    task_id="de305d54-75b4-431b-adb2-eb6b9e546014",
    user_id="admin",
    llm_model="gpt-4",
    input_tokens=1000,
    output_tokens=500,
    duration_seconds=3.5,
    success=True,
)
```

---

## Troubleshooting

### Metrics not recorded

1. Confirm `PLANEXE_TASK_ID` is set when running through task-backed services.
2. Confirm database connectivity.
3. Check logs for token instrumentation warnings/errors.

### Missing token values

Common causes:

1. Provider response does not include usage data.
2. Response shape differs from expected parser inputs.
3. Wrapper strips usage before returning response.

### `unknown` rows in token metrics

If unknown rows appear with no usage/cost, they are instrumentation noise and should be filtered out by current code.
New rows should prefer provider-attributed entries only.

### No duration values

Duration is measured via `LLM*StartEvent`/`LLM*EndEvent` correlation in TrackActivity.
If duration is missing, confirm the same service build contains the current TrackActivity implementation.

Debug extraction directly:

```python
from worker_plan_internal.llm_util.token_counter import extract_token_count

token_count = extract_token_count(your_response)
print(token_count)
```

### Database lock errors

- Avoid concurrent writers without proper pooling/transaction setup.
- Review database configuration for multi-process deployment.

---

## Performance notes

- Per-call overhead is designed to be low.
- Metrics persistence uses indexed fields for common run and model queries.
- Lazy-loading minimizes startup/import impact.

---

## Future enhancements

1. Reconciliation dashboard drill-down by user and task
2. Budget guardrails and rate limiting
3. Usage dashboards and trend analysis
4. Provider/model optimization recommendations
5. Extended cache-efficiency reporting
