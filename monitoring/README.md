# Optional local operational views

This separate R8 stack never recreates the existing MarketLab services. It has
no scheduler or external notifications. Keep it on the local machine; anonymous
Grafana access has Viewer permission and host ports bind only to loopback.

Use acquired Prometheus/Grafana images pinned to their observed repository
digests. Set R8_PROMETHEUS_IMAGE and R8_GRAFANA_IMAGE to the complete
repository:version@sha256:digest identities; the Compose file deliberately has no
floating image defaults. Inspect configuration with
`docker compose -f monitoring/compose.yaml config`, then launch this stack alone.
Use a unique `--project-name` for disposable acceptance resources and record
container/volume IDs before removing exactly that owned stack. Retention is 24h
and 512MB; each monitoring container has a 384MiB memory limit.

The supplied target ports are owned API 58009, inference worker 59110, research
worker 59111, ingestion worker 59112 and durable collector 59109. Configure the
owned API normally. For each CLI worker set MARKETLAB_METRICS_PORT to its own
port; monitoring is disabled at the default 0. The registry is shared with that
worker's actual bar/copilot/memo services, not the separate API process. Process
counters reset on restart. Finite workers disappear after exit; an `up=0` target
then means unavailable, not a failed durable job. Short-lived workers may finish
between scrapes; use durable state and acceptance evidence for their final state.

Run the separate read-only collector with
`python -m marketlab.monitoring --port 59109` against only the intended owned
database. It uses an independent one-connection pool, 2s connect/1s statement/
250ms lock bounds and polls every 5s. Scrapes read an in-memory snapshot without
DB queries. Failed or >15s-old state has `marketlab_durable_available=0` and omits
job gauges. Never sum duplicate durable collectors. Attempts/retried-job counts
are current DB aggregates (gauges), not event counters. Queue age uses DB time,
clamped at zero; the known backwards-clock discrepancy remains.

Exporters default to 127.0.0.1. Confirm that host.docker.internal can reach the
owned loopback endpoints on the current Docker Desktop runtime. If it cannot,
run owned API/workers/collector in an isolated Docker network and update the
owned target configuration. MARKETLAB_METRICS_BIND=0.0.0.0 is explicitly allowed
only for such private container networking, with any host publication still
127.0.0.1. Do not expose a host exporter on a public interface or change Docker
network/system settings to make a scrape work.

Open Grafana at http://127.0.0.1:53000/d/marketlab-r8 and Prometheus at
http://127.0.0.1:59090. Change the two host ports with R8_GRAFANA_PORT and
R8_PROMETHEUS_PORT when needed. Missing samples display as unavailable. The
dashboard's process RSS is available only where prometheus-client supports OS
process collection; it excludes children and model processes. Full benchmark
resource evidence comes from the separate R8 resource sampler with recorded
collection skew. The separate monitoring-service RSS panel uses Prometheus's
Linux process metrics from its own self-scrape. It measures only that monitoring
process and does not establish worker, model, child-process or whole-system memory.

Validate target scrapes, real worker activity, failure/recovery, query values and
rendered panels before claiming a working dashboard. A config-only setup or empty
panel is not runtime acceptance. Optional exporter bind/start/stop errors never
change worker results, job retries, leases or CLI output. The dedicated collector
returns nonzero if it cannot bind its endpoint.
