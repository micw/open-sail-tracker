# Open Sail Tracker Helm chart

This chart deploys the stateless CoAP backend and the static web application. By default, the backend pod binds UDP port `39001` directly on its Kubernetes node through `hostPort`. The backend Service resource is optional and disabled by default.

```bash
helm upgrade --install open-sail-tracker deploy/helm/open-sail-tracker \
  --namespace open-sail-tracker \
  --create-namespace \
  --set image.tag=master \
  --set web.image.tag=master
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

## Web application

The web application is enabled by default and runs as a separate non-root nginx deployment. Its ClusterIP Service listens on port `80`, and the default Ingress publishes it at the root of `https://sailtracker.wyraz.de/`:

```yaml
web:
  enabled: true
  image:
    repository: ghcr.io/micw/open-sail-tracker-web
    tag: master
  ingress:
    enabled: true
    className: nginx
    host: sailtracker.wyraz.de
    path: /
    tls:
      enabled: true
      secretName: sailtracker-wyraz-de-tls
```

The existing `/grafana/` Ingress remains more specific than the root path and continues to route to Grafana. Set `web.ingress.enabled=false` if another Ingress or reverse proxy publishes the web Service.

Branch image tags are generated from Git refs. Because `/` is not valid in a container tag, a branch such as `feature/xy` is published as `feature-xy`. Git tags such as `v1.0.0` are preserved.

This proof-of-concept endpoint is unauthenticated and must be protected or replaced before production use.
