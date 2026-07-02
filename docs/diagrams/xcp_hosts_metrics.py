from diagrams import Cluster, Diagram, Edge
from diagrams.onprem.compute import Server


graph_attr = {
    "fontsize": "18",
    "pad": "0.4",
    "splines": "ortho",
}

with Diagram(
    "XCP-ng Hosts Metrics",
    filename="docs/diagrams/xcp_hosts_metrics",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    cloud = Server("Grafana Cloud\nMimir")

    with Cluster("XCP-ng pool hosts"):
        for host in ["fett", "yoda"]:
            with Cluster(host):
                xapi = Server("XAPI")
                exporter = Server("xen-exporter\n127.0.0.1:9111")
                collector = Server("otelcol-contrib\n127.0.0.1:13133")

                xapi >> Edge(label="XAPI") >> exporter
                exporter >> Edge(label="OpenMetrics") >> collector
                collector >> Edge(label="remote_write") >> cloud
