from diagrams import Cluster, Diagram, Edge
from diagrams.k8s.compute import Deploy, DS
from diagrams.k8s.infra import Node
from diagrams.k8s.network import SVC
from diagrams.onprem.compute import Server


graph_attr = {
    "fontsize": "18",
    "pad": "0.4",
    "splines": "ortho",
}

with Diagram(
    "Kubernetes OTel Observability",
    filename="docs/diagrams/kubernetes_otel",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    cloud = Server("Grafana Cloud\nMimir + Tempo")

    with Cluster("Clusters: fett, solo, chewie"):
        node = Node("Kubernetes nodes")
        obi = DS("OBI DaemonSet")
        node_exporter = DS("otel-node-exporter")
        kube_state = Deploy("otel-kube-state-metrics")
        svc = SVC("observability-otel-collector")
        collector = Deploy("OTel Collector")

        node >> Edge(label="host metrics") >> node_exporter
        node >> Edge(label="eBPF") >> obi
        kube_state >> Edge(label="cluster state") >> collector
        node_exporter >> Edge(label="OpenMetrics") >> collector
        obi >> Edge(label="OTLP") >> svc >> collector

    collector >> Edge(label="OTLP/remote_write") >> cloud
