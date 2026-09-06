# Monitoring & Observability

Canonical runbook for the LEAP observability stack on the production VM.

- **Logs** — Loguru JSON → Promtail → Loki → Grafana
- **Metrics** — FastAPI `/metrics` + celery-exporter → Prometheus → Grafana
- **Business numbers** — Postgres role `grafana_ro` (Overview, stuck recordings)
- **Public surface** — `https://${DOMAIN}/grafana` and `/prometheus` (nginx basic auth)

Wiring lives in `docker-compose.yml` and `monitoring/`. Grafana reloads
dashboards from `monitoring/dashboards/` every 30s. CI recreates
`prometheus`, `promtail`, and `grafana` on each deploy so JSON/config
changes land without a manual step.

## Architecture

```
┌──────────────┐    structured.json  ┌──────────┐    push     ┌──────┐
│  api / celery│ ───────────────────►│ promtail │ ──────────► │ loki │
└──────────────┘                     └──────────┘             └──────┘
       │ /metrics                                              ▲
       ▼                                                       │
┌──────────────┐    scrape           ┌────────────┐   query  ┌─────────┐
│  api:8000    │ ──────────────────► │ prometheus │ ───────► │ grafana │
└──────────────┘                     └────────────┘          └─────────┘
                                           ▲
                  Redis events             │
┌──────────────┐  ──────────────► ┌──────────────────┐
│   celery     │                  │ celery_exporter  │
└──────────────┘                  └──────────────────┘
                                           ▲
Postgres (grafana_ro) ─────────────────────┘
```

`PROMETHEUS_MULTIPROC_DIR` is a shared tmpfs. API and Celery workers write
histogram files there; `/metrics` on the API process aggregates them. Pipeline
stage duration is visible in Prometheus.

Loki chunks live in Object Storage (90 days). Prometheus TSDB is local (30 days).
A dashboard window wider than 30 days is empty by design.

## Logs

HTTP (`api.middleware.logging.LoggingMiddleware`): one event per request.
Skipped: `/api/v1/health/*`, `/metrics`. `user_id` is the first 8 characters.
`X-Request-ID` is echoed so a client can correlate edge → API.

Celery (`api.celery_app` signals):

| Signal         | Level     | Notes                                      |
| -------------- | --------- | ------------------------------------------ |
| `task_prerun`  | DEBUG     | Not shipped (JSON sink is INFO)            |
| `task_postrun` | INFO/WARN | `duration_ms`, final `task_state`          |
| `task_retry`   | WARNING   |                                            |
| `task_failure` | ERROR     | `exception_class` + traceback              |

Human-readable files (`app.log`, `celery-*.log`) stay on the VM for SSH.
Only `structured.json` is shipped to Loki.

## Loki labels

Promtail promotes only low-cardinality fields
(`monitoring/promtail.yml`):

`level, module, queue, method, route, status_code, task_name, task_state, platform, exception_class`

High-cardinality fields stay in the body. After `| json` they appear as
`record_extra_*` (loguru nests them under `record.extra`):

```logql
{app="leap"} | json | record_extra_request_id = "a8f1c3..."
{app="leap", task_state="FAILURE"} | json | record_extra_recording_id = "42"
{app="leap", level=~"ERROR|CRITICAL"}
```

Do not add `request_id` / `recording_id` / `user_id` as labels.

## Metrics

### FastAPI (`leap_http_*` at `api:8000/metrics`)

`handler` is the route template (`/api/v1/recordings/{id}`), not the raw path.

| Metric                                      | Labels                    |
| ------------------------------------------- | ------------------------- |
| `leap_http_requests_total`                  | `method, handler, status` |
| `leap_http_request_duration_seconds_bucket` | `method, handler`         |
| `leap_http_requests_inprogress`             | `method, handler`         |

### Celery (`celery_exporter:9808`)

Workers must emit events (`worker_send_task_events=True`, started with `-E`).

Useful series: `celery_queue_length`, `celery_task_*_total`,
`celery_task_runtime_bucket`, `celery_worker_up`.

### Custom (`api.observability.metrics`)

| Metric                                        | Notes                                                                 |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `leap_pipeline_stage_duration_seconds`        | `track_pipeline_stage()` in processing/upload tasks                   |
| `leap_queue_oldest_task_age_seconds`          | Redis `leap:enq:<queue>`; stale members (>7d) dropped on scrape       |
| `leap_external_api_duration_seconds`          | Defined; **not wired** — do not add Grafana panels until wrappers exist |

### Health

| Endpoint                   | Use                                      |
| -------------------------- | ---------------------------------------- |
| `GET /api/v1/health/live`  | Process up. Docker probe.                |
| `GET /api/v1/health/ready` | DB + Redis + storage. 503 if any fail.   |

## Dashboards

Four JSON files in `monitoring/dashboards/`. Folder **LEAP**, home = Overview.

| File                    | UID             | Answers                                                                 |
| ----------------------- | --------------- | ----------------------------------------------------------------------- |
| `leap_overview.json`    | `leap-overview` | Users, recordings, transcribed minutes, uploads, share link traffic, stuck, failures (PG + Prometheus) |
| `leap_api.json`         | `leap-api`      | RPS / 5xx / p95 pulse (last 5m), traffic shape, top routes, 5xx logs    |
| `leap_celery.json`      | `leap-celery`   | Workers, queues, stage duration, in-flight, Celery failures             |
| `leap_errors.json`      | `leap-errors`   | ERROR pulse, exception/recording/user tables, PG failed-recordings      |

API pulse tiles ignore the dashboard time picker (`timeFrom: 5m`) so a 30-day
window does not show a stale p95 from last week's one request. Charts use
`$__rate_interval`. Pipeline success rate on Overview counts only terminal
rows (READY / UPLOADED / EXPIRED / SKIPPED / failed) — in-flight is excluded.

Share traffic on Overview is **Postgres** (`share_access_events`), grouped by
calendar day. Do not use Prometheus `increase(...[1d])` for those panels —
a sliding 24h window plus legend `sum` overcounts overlapping samples.

MTS Link “MP4 still converting” is an INFO parking path, not an ERROR / retry.

## PromQL / LogQL

```promql
topk(10, sum by (handler) (rate(leap_http_requests_total[$__rate_interval])))

100 * sum(rate(leap_http_requests_total{status=~"5.."}[5m]))
  / clamp_min(sum(rate(leap_http_requests_total[5m])), 1e-9) or vector(0)

histogram_quantile(0.95,
  sum by (handler, le) (rate(leap_http_request_duration_seconds_bucket[$__rate_interval])))

celery_queue_length
leap_queue_oldest_task_age_seconds
```

```logql
{app="leap", level=~"ERROR|CRITICAL"} | json | line_format "{{.text}}"
{app="leap"} | json | record_extra_recording_id = "42"
```

## Environment

| Variable                        | Default                     | Purpose                              |
| ------------------------------- | --------------------------- | ------------------------------------ |
| `JSON_LOG_FILE`                 | `/app/logs/structured.json` | Promtail tail                        |
| `LOG_FILE` / `ERROR_LOG_FILE`   | `/app/logs/app.log`         | Human ops files, not shipped         |
| `LOG_LEVEL`                     | `INFO`                      | Console / Loguru                     |
| `MONITORING_PROMETHEUS_ENABLED` | `true`                      | Mount `/metrics`                     |
| `LOKI_S3_BUCKET` + access keys  | —                           | Loki object storage                  |
| `GRAFANA_RO_PASSWORD`           | —                           | Postgres datasource                  |
| `GRAFANA_USER` / `GRAFANA_PASSWORD` | `admin`                 | Grafana login (htpasswd uses the same password) |

## Failure modes

| Symptom                                      | Cause                                              | Fix                                                                 |
| -------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------- |
| Overview / PG panels empty                   | `grafana_ro` missing or password mismatch          | Set `GRAFANA_RO_PASSWORD`; migrations **023**, **025**, **045**; restart Grafana |
| API pulse p95 looks huge on a 30d window     | Fixed in `leap_api.json` v2 (pulse is last 5m)     | Redeploy Grafana JSON                                               |
| Slowest-routes table is empty                | Too few requests in range for a stable p95 | v3 uses ≥3 requests over `$__range`                                 |
| Loki exception table empty                   | Query parsed JSON `exception_class`        | Use label `{exception_class=~".+"}` (task_failure only)             |
| Share downloads legend in the thousands      | `increase[1d]` + legend `sum` on overlap   | Overview v6 reads `share_access_events` by calendar day             |
| Oldest task age is weeks with queue depth 0  | Stale `leap:enq:*` ZSET member             | Prerun/postrun zrem all queues; scrape drops members older than 7d  |
| MTS pending fills Errors dashboard           | Logged ERROR + Celery retry                | Pending conversion is INFO and does not retry                       |
| Loki panels empty                            | App not writing `structured.json`                  | Check `JSON_LOG_FILE` in the container                              |
| `leap-api` Prometheus target DOWN            | `/metrics` off                                     | `MONITORING_PROMETHEUS_ENABLED=true` on **api**                     |
| `celery_queue_length` always 0               | Workers not sending events                         | `-E` + `worker_send_task_events=True` (already in compose)          |
| `leap_celery_worker` Docker **unhealthy**    | Healthcheck script can fail while tasks still run  | Confirm with `docker compose logs celery_worker`; do not trust the badge alone |
| External API Grafana panels                  | Removed — `track_external_api()` is unused         | Wire the helper before adding panels back                           |

## Cardinality

Keep labels bounded. Current mix stays under ~1000 Loki streams and ~10k
Prometheus series on a single VM. Do the math before adding a label.

## See also

- `backend/api/middleware/logging.py`
- `backend/api/observability/metrics.py`
- `backend/api/celery_app.py`
- `backend/logger.py`
- `guides/DEPLOYMENT.md` — SMTP / Lockbox (transactional email is not this stack)
