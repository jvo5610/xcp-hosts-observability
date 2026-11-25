# Operations

## Fett local Solo recovery (2026-11-25)

The physical host is `root@100.109.20.74:22`. Only its local collector destination
was changed from the retired `solo-cp.burro-fujita.ts.net:30418` to the retained
private gateway `http://100.111.88.68:30418`. This independent producer is not
covered by the Kubernetes collector manifests in the Argo repository.

`scripts/deploy-solo-otlp.py` runs locally (Python with boto3 for `--apply`). It
copies the non-secret, Python3.6-compatible helper, checks the exact Fett hostname,
and obtains `/observability/solo/otlp-gateway/authorization-b64` from SSM in
`us-east-1`. The credential travels only over SSH stdin and is stored remotely in
`/etc/otelcol-contrib/solo-otlp.env` mode0600. A systemd drop-in loads that file;
the collector YAML references the variable rather than storing a literal header.

```sh
python scripts/deploy-solo-otlp.py                 # check only
python scripts/deploy-solo-otlp.py --apply
python scripts/deploy-solo-otlp.py --rollback /root/solo-otlp-collector-recovery-TIMESTAMP
```

The helper changes only the `otlphttp/local` endpoint/header, its new environment
file and its own drop-in. It preserves the Cloud exporter block byte-for-byte,
validates with the installed0.155.0 binary, and restarts only `otelcol-contrib`.
Root-only backups include the old config and unit. Rollback checks current hashes
and restores only the three modified files. A failed restart automatically restores
the prior files and restarts the collector. Never open exporter port9111 or alter
XAPI/VMs to solve a collector-delivery problem. Do not print environment files,
complete host configs, credentials or real telemetry payloads.

Applied backup: `/root/solo-otlp-collector-recovery-20261125T033831Z`.
The exporter continued returning HTTP200; the recovered collector sent local metric
points and the Xen `up` signal returned to Solo Mimir. The legacy Cloud destination
was already failing and was deliberately left unchanged.

## Fett clock: gradual correction only

Fett was about216seconds ahead of two agreeing NTP references (LAN
`192.168.4.1` and Cloudflare `162.159.200.1`), with chrony unsynchronized and all
four DNS-based sources unresolved. This can timestamp telemetry in the future,
so immediate-query freshness alone is insufficient until the clock converges.

`scripts/configure-fett-ntp.py` is Fett-only and configures those two tested IP
sources, removes automatic initial-step directives and limits slew to5000ppm
(0.5%). It backs up the old config, validates a state-isolated copy with
`chronyd -Q` (measurement only), and restarts only chronyd. It checks wall-clock
continuity against monotonic time. No manual clock step, `clock_settime`, global
DNS change, RTC command, host restart or XAPI/VM operation is performed.

```sh
scp scripts/configure-fett-ntp.py root@100.109.20.74:/root/solo-otlp-recovery/
ssh root@100.109.20.74 'python3 /root/solo-otlp-recovery/configure-fett-ntp.py'
ssh root@100.109.20.74 'python3 /root/solo-otlp-recovery/configure-fett-ntp.py --apply'
ssh root@100.109.20.74 'chronyc tracking; chronyc -n sources -v'
```

Convergence from216seconds at the conservative maximum rate takes approximately
12hours. Require a selected source, decreasing residual offset, no clock jump,
increasing successful local exports, and alert recovery; do not claim zero clock
skew before it is measured. Preserve backups. Any NTP rollback must keep automatic
stepping disabled: do not blindly restore the former `makestep` directive.

Grafana rules belong to the `argocd` repository; the Grafana rule and delivery
logic were not modified by these host helpers.

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
