# Open Sail Tracker Helm chart

This chart deploys the stateless CoAP backend. By default, the pod binds UDP port `39001` directly on its Kubernetes node through `hostPort`. The Service resource is optional and disabled by default.

```bash
helm upgrade --install open-sail-tracker deploy/helm/open-sail-tracker \
  --namespace open-sail-tracker \
  --create-namespace \
  --set image.tag=master
```

The node must accept and route public UDP traffic on port `39001`. Only one pod using this host port can run on a node. Keep `replicaCount: 1` or use scheduling constraints that place replicas on different nodes.

To restrict the socket to one node address, set `hostPort.hostIP`. To disable the host port and create a Service instead:

```yaml
hostPort:
  enabled: false

service:
  enabled: true
  type: LoadBalancer
  port: 39001
  externalTrafficPolicy: Local
```

## VictoriaMetrics

Persistence is enabled by default and targets the VictoriaMetrics service in the same namespace:

```yaml
victoriaMetrics:
  enabled: true
  url: http://open-sail-tracker-vm:8428/api/v1/import/prometheus
  queueSize: 10000
```

The URL is injected as `VICTORIA_METRICS_URL`. Set `victoriaMetrics.enabled=false` to run the logging-only backend. The chart does not install VictoriaMetrics itself; the `open-sail-tracker-vm` Service must already exist or the URL must be overridden.

Branch image tags are generated from Git refs. Because `/` is not valid in a container tag, a branch such as `feature/xy` is published as `feature-xy`. Git tags such as `v1.0.0` are preserved.

This proof-of-concept endpoint is unauthenticated and must be protected or replaced before production use.
