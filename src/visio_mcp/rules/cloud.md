# Cloud architecture

**Use when:** you need to show which Azure, AWS or Google Cloud services implement a system and how they are scoped and connected.

## Purpose
A provider-specific architecture with official service icons, drawn the way the
provider's own reference architectures are: Azure Architecture Center, AWS
Architecture Icons group guidelines, Google Cloud architecture diagrams. Read the
provider file (`cloud-azure`, `cloud-aws`, `cloud-gcp`) for its group hierarchy and
service kinds.

## Spec settings
- `"type": "cloud"`, `"layout": "flowchart-lr"` (users/internet on the left, data on
  the right).
- Theme `auto` picks `azure`, `aws` or `gcp` from the dominant provider of your kinds.
- One provider per diagram (`[mixed-providers]`). For true multi-cloud, give each
  provider its own group of kind `cloud`.

## Node kinds
- Provider-prefixed kinds for every cloud service: `azure-functions`, `aws-lambda`,
  `gcp-cloud-run` ... (`list_kinds`). A cloud diagram with generic boxes only gets
  `[provider-kinds]`.
- Generic kinds only for what is not a cloud service: `user`, `client`, `mobile`,
  `external` (SaaS, on-prem systems), `internet`.
- Label with the role, not just the service: `Orders API` with technology
  `Azure Container Apps`, or simply the official service name when there is one
  instance (`Amazon S3`).

## Groups (scopes, outer to inner)
| Group kind | Azure | AWS | Google Cloud |
|---|---|---|---|
| `cloud` | Subscription / resource group | AWS Cloud / account | Project |
| `region` | Region | Region | Region |
| `network` | Virtual network | VPC | VPC network |
| `zone` | Availability zone | Availability Zone | Zone |
| `subnet` | Subnet | Public/private subnet | Subnet |
| `cluster` | AKS cluster | EKS/ECS cluster | GKE cluster |

Nest outer to inner (`[nesting-order]`), at most 4 levels (`[nesting]`). Global/edge
services (CDN, DNS, front door, IAM, monitoring) sit outside the region; PaaS without
VNet integration sits in the region but outside the network.

## Edges
- Label with protocol or action: `HTTPS`, `SQL`, `AMQP`, `triggers`, `stores`,
  `private endpoint`.
- `dashed` for async (queues, events, change feeds); `dotted` for monitoring, logging,
  identity lookups if you show them at all.
- Show the request path end to end; leave cross-cutting services (monitoring, Key
  Vault) with one edge or none, placed at the side.

## Checklist
- [ ] One provider, official service names, provider kinds
- [ ] Scope groups nested account > region > network > subnet
- [ ] Global services outside the region
- [ ] Edges labeled; async dashed
- [ ] Title names the workload and environment (`Prod`, `West Europe`)

## Common mistakes
- Generic shapes with "Lambda" in the label instead of the provider kind.
- Every service inside the VNet/VPC (most PaaS is not).
- Icons without labels, or labels that just repeat the icon for many instances.
- Monitoring and identity arrows to every node: drop them or show once.

## Example
```json
{
  "title": "Contoso Web Shop - Azure",
  "subtitle": "Production, West Europe - v1.0",
  "type": "cloud",
  "layout": "flowchart-lr",
  "groups": [
    {"id": "sub", "label": "Production Subscription", "kind": "cloud"},
    {"id": "region", "label": "West Europe", "kind": "region", "parent": "sub"},
    {"id": "vnet", "label": "Shop VNet", "kind": "network", "parent": "region"},
    {"id": "app_subnet", "label": "App Subnet", "kind": "subnet", "parent": "vnet"}
  ],
  "nodes": [
    {"id": "shopper", "label": "Shopper", "kind": "user"},
    {"id": "frontdoor", "label": "Azure Front Door", "kind": "azure-front-door", "group": "sub"},
    {"id": "web", "label": "Storefront", "kind": "azure-app-service", "group": "app_subnet"},
    {"id": "api", "label": "Orders API", "kind": "azure-functions", "group": "app_subnet"},
    {"id": "bus", "label": "Order Queue", "kind": "azure-service-bus", "group": "region"},
    {"id": "sql", "label": "Orders Database", "kind": "azure-sql-database", "group": "region"},
    {"id": "vault", "label": "Key Vault", "kind": "azure-key-vault", "group": "region"}
  ],
  "edges": [
    {"source": "shopper", "target": "frontdoor", "label": "HTTPS"},
    {"source": "frontdoor", "target": "web", "label": "HTTPS"},
    {"source": "web", "target": "api", "label": "REST"},
    {"source": "api", "target": "sql", "label": "SQL"},
    {"source": "api", "target": "bus", "label": "enqueues", "style": "dashed"},
    {"source": "api", "target": "vault", "label": "reads secrets", "style": "dotted"}
  ]
}
```
