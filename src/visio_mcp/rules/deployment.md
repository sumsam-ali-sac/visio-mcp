# Deployment

**Use when:** you need to show what runs where: environments, hosts, clusters and the networks between them.

## Purpose
Maps software (containers/services) onto infrastructure: environments, clusters,
nodes, VMs, managed services and the network paths between them. It answers "where
does this run, how many, and how does traffic reach it?" for operators, SRE and
security reviews. (C4 calls this the deployment diagram.)

## Spec settings
- `"type": "deployment"`, `"layout": "flowchart-lr"` (ingress left, data right).
- Theme `professional`; use `cloud` type instead if the audience wants provider icons.

## Node kinds
| Kind | Use for |
|---|---|
| `server`, `pc` | VMs, physical hosts, workstations. |
| `service`, `api`, `webapp`, `function` | Deployed software instances (put the runtime in `technology`). |
| `database`, `cache`, `storage`, `queue` | Managed or self-hosted stores and brokers. |
| `loadbalancer`, `gateway`, `firewall` | Ingress, API gateways, firewalls. |
| `internet`, `user`, `external` | Outside-world endpoints. |

Put instance counts and sizes in `description` (`3 replicas, 2 vCPU`), not in labels.

## Groups (outer to inner)
`environment` (Prod, Staging) > `region`/data centre > `network` > `subnet` >
`cluster` (Kubernetes, VM scale set) > nodes. Keep to 4 levels; drop levels that do
not change anything for the reader.

## Edges
- Label with protocol and port when it matters for operations: `HTTPS 443`,
  `TCP 5432`, `AMQP`.
- `dashed` for async and replication; two-way arrows only for real symmetric
  replication or peering.
- Show the inbound path from the internet explicitly; it is what reviewers check.

## Checklist
- [ ] Every deployable is in exactly one execution environment group
- [ ] Environment and region named in title or groups
- [ ] Ingress path from internet visible and labeled
- [ ] Ports/protocols on edges crossing network boundaries
- [ ] Replicas/sizes in descriptions, not duplicated boxes

## Common mistakes
- Mixing two environments in one diagram without separate `environment` groups.
- Drawing every replica as its own node.
- Logical components with no host - that's an architecture diagram.
- Deep nesting with single-node groups at each level.

## Example
```json
{
  "title": "Orders Platform - Production Deployment",
  "subtitle": "Prod, single region - Oct 2026",
  "type": "deployment",
  "layout": "flowchart-lr",
  "groups": [
    {"id": "prod", "label": "Production", "kind": "environment"},
    {"id": "dmz", "label": "DMZ Subnet", "kind": "subnet", "parent": "prod"},
    {"id": "k8s", "label": "Kubernetes Cluster", "kind": "cluster", "parent": "prod"},
    {"id": "data", "label": "Data Subnet", "kind": "subnet", "parent": "prod"}
  ],
  "nodes": [
    {"id": "internet", "label": "Internet", "kind": "internet"},
    {"id": "lb", "label": "Load Balancer", "kind": "loadbalancer", "group": "dmz", "technology": "NGINX"},
    {"id": "web", "label": "Web Frontend", "kind": "webapp", "group": "k8s", "technology": "Next.js", "description": "3 replicas"},
    {"id": "api", "label": "Orders API", "kind": "api", "group": "k8s", "technology": "Python / FastAPI", "description": "4 replicas"},
    {"id": "worker", "label": "Billing Worker", "kind": "service", "group": "k8s", "technology": "Go", "description": "2 replicas"},
    {"id": "db", "label": "Orders DB", "kind": "database", "group": "data", "technology": "PostgreSQL 16", "description": "Primary + standby"},
    {"id": "mq", "label": "Message Broker", "kind": "queue", "group": "data", "technology": "RabbitMQ"}
  ],
  "edges": [
    {"source": "internet", "target": "lb", "label": "HTTPS 443"},
    {"source": "lb", "target": "web", "label": "HTTP 8080"},
    {"source": "web", "target": "api", "label": "HTTP 8000"},
    {"source": "api", "target": "db", "label": "TCP 5432"},
    {"source": "api", "target": "mq", "label": "AMQP 5672", "style": "dashed"},
    {"source": "mq", "target": "worker", "label": "AMQP 5672", "style": "dashed"}
  ]
}
```
