# Operations

## Validate Host Services

Run on each XCP-ng host:

```bash
systemctl is-active xen-exporter otelcol-contrib
ss -ltnp | grep -E '(9111|13133)'
curl -fsS http://127.0.0.1:9111/metrics | head
curl -fsS http://127.0.0.1:13133/
```

Expected listeners:

- `127.0.0.1:9111`: `xen-exporter`
- `127.0.0.1:13133`: OTel Collector health check

## Validate Grafana Cloud Metrics

Use the Grafana API token from `~/.grafana` and query:

```promql
xen_collector_duration_seconds{job="integrations/xen-exporter"}
```

Expected active `instance` label values:

- `fett`
- `yoda`

## Local Config Files

On each host:

```text
/etc/xen-exporter/xen-exporter.env
/etc/otelcol-contrib/config.yaml
/etc/otelcol-contrib/grafana-cloud.env
/etc/systemd/system/otelcol-contrib.service.d/env.conf
```

Do not print or commit the contents of the env files; they contain credentials.

## Rollback

Rollback should prefer disabling remote write or stopping the collector rather
than reinstalling Alloy:

```bash
systemctl stop otelcol-contrib
systemctl status xen-exporter
```

If the collector must be restored, reinstall `otelcol-contrib` and put the
Grafana Cloud API key back into `/etc/otelcol-contrib/grafana-cloud.env`.
