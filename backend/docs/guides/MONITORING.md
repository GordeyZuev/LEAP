# Monitoring & Observability

This is the canonical runbook for the LEAP observability stack:

- **Logs** — Loguru (structured JSON) → Promtail → Loki → Grafana
- **Metrics** — FastAPI + Celery → Prometheus → Grafana
- **Dashboards** — `monitoring/dashboards/leap_*.json` (auto-provisioned)
- **Public surface** — `https://${DOMAIN}/grafana` (basic auth) and
  `https://${DOMAIN}/prometheus` (basic auth)

## Architecture

```
┌──────────────┐    JSON file       ┌──────────┐    push        ┌──────┐
│  api / celery│ ──structured.json──│ promtail │ ─────────────► │ loki │
└──────────────┘                    └──────────┘                └──────┘
       │                                                            ▲
       │ /metrics                                                   │ query
       ▼                                                            │
┌──────────────┐    scrape          ┌────────────┐    query   ┌─────────┐
│  api:8000    │ ─────────────────► │ prometheus │ ─────────► │ grafana │
└──────────────┘                    └────────────┘            └─────────┘
                                          ▲
                  Redis events            │ scrape
┌──────────────┐  ──────────────► ┌──────────────────┐
│   celery     │                   │ celery_exporter  │
└──────────────┘                   └──────────────────┘
```

All wiring lives in `docker-compose.yml` and `monitoring/`. Both datasources
are auto-provisioned by Grafana on startup; dashboards are picked up from
`monitoring/dashboards/` and reload every 30s.

## What gets logged

### HTTP access log (`api.middleware.logging.LoggingMiddleware`)

One INFO event per request with structured fields:

| Field         | Source                          | Example                             |
| ------------- | ------------------------------- | ----------------------------------- |
| `request_id`  | `X-Request-ID` header or uuid4  | `a8f1...`                           |
| `method`      | HTTP verb                       | `GET`                               |
| `path`        | Raw URL path                    | `/api/v1/recordings/42`             |
| `route`       | FastAPI route template          | `/api/v1/recordings/{id}`           |
| `status_code` | Response status                 | `200`                               |
| `duration_ms` | Wall-clock                      | `12.3`                              |
| `user_id`     | First 8 chars of authed user id | `01KFHA26`                          |
| `client_ip`   | Trusted `X-Forwarded-For`       | `203.0.113.5`                       |
| `bytes_sent`  | `Content-Length` header         | `1842`                              |

`/api/v1/health` and `/metrics` are excluded to keep the signal clean.
The middleware also echoes `X-Request-ID` back so a client trace spans
edge → backend.

### Celery task lifecycle (`api.celery_app` signals)

| Signal         | Level     | Fields added                                          |
| -------------- | --------- | ----------------------------------------------------- |
| `task_prerun`  | DEBUG     | `task_id`, `task_name`, `queue`, `task_state=STARTED` |
| `task_postrun` | INFO/WARN | + `duration_ms`, final `task_state`                   |
| `task_retry`   | WARNING   | + `task_state=RETRY`                                  |
| `task_failure` | ERROR     | + `exception_class`, exception traceback              |

## Label policy (Loki)

Streams are cheap; **labels are not**. Promtail promotes only **low-cardinality**
fields to labels (`monitoring/promtail.yml`):

> `level, module, queue, method, route, status_code, task_name, task_state, platform, exception_class`

High-cardinality fields (`request_id`, `task_id`, `recording_id`, `user_id`,
`duration_ms`) stay in the log body and are queried with `| json` in LogQL.
After `| json`, Loki flattens loguru's nested structure with underscore
separators, so the original `record.extra.request_id` becomes the extracted
key `record_extra_request_id`:

```logql
{app="leap"} | json | record_extra_request_id = "a8f1c3..."
{app="leap", task_state="FAILURE"} | json | record_extra_recording_id = "42"
```

Putting these in labels would create one stream per unique value — at our
RPS that explodes the Loki index within hours.

## Metrics namespace

### FastAPI (`prometheus-fastapi-instrumentator`)

Exposed at `http://api:8000/metrics`, prefix `leap_http_*`:

| Metric                                       | Type      | Labels                       |
| -------------------------------------------- | --------- | ---------------------------- |
| `leap_http_requests_total`                   | counter   | `method, handler, status`    |
| `leap_http_request_duration_seconds_bucket`  | histogram | `method, handler` (+ `le`)   |
| `leap_http_request_size_bytes_*`             | summary   | `method, handler`            |
| `leap_http_response_size_bytes_*`            | summary   | `method, handler`            |
| `leap_http_requests_inprogress`              | gauge     | `method, handler`            |

`handler` is always the **route template** (`/api/v1/recordings/{id}`) —
cardinality stays bounded regardless of traffic.

### Celery (`danihodovic/celery-exporter`)

Exposed at `http://celery_exporter:9808/metrics`:

| Metric                              | Type      | Labels                |
| ----------------------------------- | --------- | --------------------- |
| `celery_queue_length`               | gauge     | `queue_name`          |
| `celery_task_sent_total`            | counter   | `name, queue_name`    |
| `celery_task_received_total`        | counter   | `name`                |
| `celery_task_started_total`         | counter   | `name`                |
| `celery_task_succeeded_total`       | counter   | `name`                |
| `celery_task_failed_total`          | counter   | `name, exception`     |
| `celery_task_retried_total`         | counter   | `name`                |
| `celery_task_runtime_bucket`        | histogram | `name` (+ `le`)       |
| `celery_worker_up`                  | gauge     | `hostname`            |

### Custom LEAP metrics (`backend/api/observability/metrics.py`)

Exposed on the same `http://api:8000/metrics` endpoint:

| Metric                                          | Type      | Labels                                  |
| ----------------------------------------------- | --------- | --------------------------------------- |
| `leap_pipeline_stage_duration_seconds_bucket`   | histogram | `stage, platform, status` (+ `le`)      |
| `leap_pipeline_recording_total`                 | counter   | `outcome, platform`                     |
| `leap_external_api_duration_seconds_bucket`     | histogram | `provider, endpoint, status` (+ `le`)   |
| `leap_queue_oldest_task_age_seconds`            | gauge     | `queue`                                 |

- `stage` ∈ {`download`, `trim`, `transcribe`, `extract_topics`,
  `generate_subtitles`, `upload`}.
- `status` ∈ {`success`, `failure`} — recorded by the
  `track_pipeline_stage` / `track_external_api` context managers in
  `api.observability.metrics`.
- `leap_queue_oldest_task_age_seconds` is implemented as a lazy collector
  that reads a Redis sorted set (`leap:enq:<queue>`) on every scrape. The
  set is populated by the `before_task_publish` signal in `celery_app.py`
  and cleaned by `task_prerun`.

### Health endpoints (`backend/api/routers/health.py`)

| Endpoint                  | Purpose                                                 |
| ------------------------- | ------------------------------------------------------- |
| `GET /api/v1/health/live` | Process is alive. No external calls. Docker probe.      |
| `GET /api/v1/health/ready`| DB + Redis + storage backend reachable. LB / Grafana.   |

`/ready` returns `503` with a JSON body
`{ready: false, checks: {db: "ok", redis: "fail", storage: "ok"}}` when any
dependency probe fails. The storage check (S3 `head_bucket`) is cached for
60 s so per-scrape readiness probes don't hammer the bucket.

## Useful queries

### LogQL

```logql
# Errors only
{app="leap", level=~"ERROR|CRITICAL"}

# All requests for a specific user (last 1h)
{app="leap", module="http.access"} | json | record_extra_user_id = "01KFHA26"

# Tail a single recording across the whole pipeline
{app="leap"} | json | record_extra_recording_id = "42"

# Failed Celery tasks with their exception class
{app="leap", task_state="FAILURE", exception_class="ValueError"}
```

### PromQL

```promql
# RPS by route, top 10
topk(10, sum by (handler) (rate(leap_http_requests_total[5m])))

# 5xx error rate as percentage
100 * sum(rate(leap_http_requests_total{status=~"5.."}[5m]))
  / sum(rate(leap_http_requests_total[5m]))

# API latency p95
histogram_quantile(0.95,
  sum by (handler, le) (rate(leap_http_request_duration_seconds_bucket[5m])))

# Celery queue depth
celery_queue_length

# Task failure rate
sum(rate(celery_task_failed_total[5m])) by (name)
```

## Environment variables

| Variable                            | Default                          | Purpose                                        |
| ----------------------------------- | -------------------------------- | ---------------------------------------------- |
| `JSON_LOG_FILE`                     | `/app/logs/structured.json`      | Loguru JSON sink (Promtail tails this)         |
| `LOG_FILE`                          | `/app/logs/app.log`              | Plain-text file sink (human ops, not shipped)  |
| `ERROR_LOG_FILE`                    | `/app/logs/error.log`            | Plain-text error-only sink                     |
| `LOG_LEVEL`                         | `INFO`                           | Loguru console level                           |
| `MONITORING_PROMETHEUS_ENABLED`     | `true`                           | Mount `/metrics` endpoint                      |
| `LOKI_S3_BUCKET`                    | —                                | Yandex Object Storage bucket for Loki chunks   |
| `LOKI_S3_ACCESS_KEY_ID`             | —                                | Service-account static access key id           |
| `LOKI_S3_SECRET_ACCESS_KEY`         | —                                | Service-account static secret                  |
| `GRAFANA_RO_PASSWORD`               | `rotate-me-immediately`          | PG password for `grafana_ro` read-only role    |

All four are wired into `api`, `celery_worker`, `celery_beat` in
`docker-compose.yml` with `${VAR:-default}` so production `.env` can override
without redeploying.

## Dashboards

Dashboards are deliberately small — only the panels that answer questions an
operator/owner actually asks. Add panels only when an incident or product
question forces the need, not pre-emptively.

| File                                    | UID              | Panels | What it answers                                                  |
| --------------------------------------- | ---------------- | -----: | ---------------------------------------------------------------- |
| `dashboards/leap_overview.json`         | `leap-overview`  | 11     | **Default home.** Business: active users, recordings, uploads, MRR, success rate, top users, upload success by platform, stuck recordings, failed by stage. |
| `dashboards/leap_pipeline.json`         | `leap-pipeline`  |  6     | Pipeline: 24h throughput, stage duration p50/p95/p99, stage failure %, recordings in flight by status. |
| `dashboards/leap_api.json`              | `leap-api`       | 10     | API: RPS, 5xx%, p95, 4xx%, latency percentiles, RPS by HTTP method, top routes by RPS / p95, 5xx by route + recent 5xx logs. |
| `dashboards/leap_celery.json`           | `leap-celery`    |  7     | Celery: failure rate, active workers, pending tasks, per-queue depth + oldest task age, failures by task name + recent failures logs. |
| `dashboards/leap_errors.json`           | `leap-errors`    |  6     | Errors: ERROR/CRITICAL count, distinct affected recordings, top exception types, recent ERRORs, errors grouped by recording_id and user_id. |

Auto-provisioned from `monitoring/grafana_dashboards.yml` — drop a new JSON
into `monitoring/dashboards/`, redeploy, Grafana picks it up within 30s.

## Rolling out to an already-deployed VM

The regular CI deploy uses `docker compose up -d --no-deps api celery_worker
celery_beat flower frontend` — it deliberately does **not** touch
infrastructure containers. New observability containers (`prometheus`,
`celery_exporter`) and config-file changes (`promtail`, `grafana`,
`nginx`) need a one-time bring-up:

```bash
ssh ubuntu@$VPS
cd /opt/leap

# 1. New images / configs are already on disk thanks to rsync in deploy.yml.
#    Pull the app images on the new SHA (already done by CI):
# docker compose pull api celery_worker celery_beat

# 2. Recreate app containers so they pick up JSON_LOG_FILE and emit JSON logs.
docker compose up -d --no-deps --force-recreate api celery_worker celery_beat

# 3. Start the new infra services.
docker compose up -d prometheus celery_exporter

# 4. Reload existing infra so it picks up new configs:
docker compose restart promtail grafana

# 5. nginx active config (`nginx/nginx.conf`) is a gitignored runtime artifact —
#    point it at the updated https template and reload.
cp nginx/nginx.https.conf nginx/nginx.conf
docker compose exec nginx nginx -s reload
```

After this is done once, subsequent CI deploys keep the observability
stack running on the existing config — no further manual steps unless
`monitoring/promtail.yml` or `monitoring/prometheus.yml` change (in which
case repeat steps 4 + recreate prometheus).

### Verification

```bash
# Structured JSON is being written:
docker compose exec api tail -n 1 /app/logs/structured.json | jq '.record.extra'

# Promtail is shipping (positions move forward):
docker compose exec promtail cat /tmp/positions.yaml

# Prometheus has targets:
curl -s http://localhost:9090/prometheus/api/v1/targets | jq '.data.activeTargets[].labels.job'

# Grafana sees both datasources:
# open https://${DOMAIN}/grafana/datasources — both Loki and Prometheus must be green
```

## Cardinality budget

A rough budget to stay healthy on a single-VM Loki/Prometheus:

- Loki streams: target <1000 active streams. Current labels at full mix:
  `level (5) × module (~50) × route (~50) × status_code (~30) × method (~7)` —
  most combinations are sparse so we sit well under the limit.
- Prometheus series: `leap_http_request_duration_seconds_bucket` is the
  big one — `handler × method × le` ≈ 50 × 7 × 11 ≈ 3 800 series. Add
  `_count` / `_sum` and the total per-API stays under 10 000. Celery
  exporter adds ~2 000. Comfortable under 30k total on a single node.

If you add a new label, do the math first.

## Failure modes

| Symptom                                                | Likely cause                                                      | Fix                                                      |
| ------------------------------------------------------ | ----------------------------------------------------------------- | -------------------------------------------------------- |
| Grafana panels empty, "No data"                        | App not writing `structured.json`                                 | Check `JSON_LOG_FILE` env in container; restart app      |
| Loki has data but `level`/`module` labels are missing  | Promtail config out of sync with loguru's `serialize=True` schema | Restart promtail; verify with `promtail --check-config`  |
| Prometheus targets DOWN for `leap-api`                 | `/metrics` not exposed                                            | Confirm `MONITORING_PROMETHEUS_ENABLED=true`             |
| `celery_queue_length` always 0                         | celery-exporter can't read events                                 | Worker must run with default `worker_send_task_events`   |
| `request_id` blank in logs                             | Middleware order — `LoggingMiddleware` registered after handlers  | Keep `app.add_middleware(LoggingMiddleware)` in `main.py` |

## See also

- `backend/api/middleware/logging.py` — HTTP middleware implementation
- `backend/api/observability/metrics.py` — Prometheus wiring
- `backend/api/celery_app.py` — Celery lifecycle signal handlers
- `backend/logger.py` — Loguru setup, sinks, format helpers
