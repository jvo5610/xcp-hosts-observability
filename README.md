# XCP-ng Hosts Observability

This repository documents the current observability setup for the XCP-ng hosts
`fett` and `yoda`.

## Current State

Both XCP-ng hosts run:

- `xen-exporter` as a local XAPI/OpenMetrics exporter on `127.0.0.1:9111`.
- `otelcol-contrib` as the local OpenTelemetry Collector on `127.0.0.1:13133`.
- A Prometheus receiver in the collector that scrapes `xen-exporter`.
- A `prometheusremotewrite` exporter that sends metrics to Grafana Cloud Mimir.

Alloy and the old node-exporter/textfile based observability path were removed.

## Hosts

| Host | Role | Exporter | Collector | Status |
| --- | --- | --- | --- | --- |
| `fett` | XCP-ng pool host | `xen-exporter` | `otelcol-contrib` | active |
| `yoda` | XCP-ng pool host | `xen-exporter` | `otelcol-contrib` | active |

## Grafana Cloud

Metrics are sent to the Willow Grafana Cloud stack:

- Grafana: `https://willowsf.grafana.net/`
- Metrics datasource UID: `grafanacloud-prom`
- Metrics remote write user: `3345330`

The remote write API key is not stored in this repository. It is stored in AWS
SSM Parameter Store at:

```text
/grafana-cloud/willowsf/alloy/rw-api-key
```

The historical name still says `alloy`, but the key is now used by OTel
Collector as well.

## Related Kubernetes Observability

Kubernetes clusters now use the GitOps app in the `argocd` repository:

```text
platform/applications/observability-otel-*
platform/manifests/observability-otel/
```

That path deploys:

- OpenTelemetry Collector
- OBI eBPF instrumentation
- lightweight `kube-state-metrics`
- lightweight `node-exporter`
- ExternalSecret for the Grafana Cloud remote write key

The previous in-cluster Grafana/Mimir/Loki/Tempo/Prometheus stacks were
deprecated in favor of Grafana Cloud as the backend.

## Diagrams

Mingrammer diagram sources live under `docs/diagrams/`.

Render them with:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python docs/diagrams/xcp_hosts_metrics.py
python docs/diagrams/kubernetes_otel.py
```

Generated PNG files are written into `docs/diagrams/`.
