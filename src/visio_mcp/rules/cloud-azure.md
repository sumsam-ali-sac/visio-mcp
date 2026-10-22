# Microsoft Azure conventions

Follow the Azure Architecture Center: official Azure icons, service names exactly as
Microsoft writes them, scopes drawn as nested containers, request path left to right.

## Group hierarchy (outer to inner)
| Scope | Group kind | Label example |
|---|---|---|
| Microsoft Entra tenant (rarely needed) | `cloud` | `Contoso Tenant` |
| Subscription / resource group | `cloud` | `Production Subscription`, `rg-shop-prod` |
| Region | `region` | `West Europe` |
| Virtual network | `network` | `vnet-shop-prod 10.1.0.0/16` |
| Availability zone (only when zonal design matters) | `zone` | `Zone 1` |
| Subnet | `subnet` | `snet-app 10.1.1.0/24` |
| AKS cluster / App Service Environment | `cluster` | `AKS Cluster` |

- Global services sit outside the region: Azure Front Door, Azure DNS, Microsoft Entra
  ID, Azure CDN, Traffic Manager.
- PaaS services without VNet integration (Storage, Cosmos DB, Service Bus, Key Vault)
  sit in the region, outside the VNet; draw a `private endpoint` edge if they are
  reached privately.
- Use the subscription OR the resource group as the outer `cloud` group, not both,
  unless the diagram is about landing zones.

## Kinds (provider-prefixed; confirm with `list_kinds`)
- Compute: `azure-app-service`, `azure-functions`, `azure-container-apps`, `azure-aks`,
  `azure-vm`, `azure-static-web-apps`.
- Data: `azure-sql-database`, `azure-cosmos-db`, `azure-storage-account`,
  `azure-blob-storage`, `azure-redis`, `azure-container-registry`.
- Integration: `azure-service-bus`, `azure-event-grid`, `azure-event-hubs`,
  `azure-api-management`, `azure-logic-apps`, `azure-data-factory`.
- Networking: `azure-front-door`, `azure-application-gateway`, `azure-load-balancer`,
  `azure-vnet`, `azure-dns`, `azure-cdn`.
- Security/identity: `azure-key-vault`, `azure-entra-id`, `azure-firewall`,
  `azure-bastion`.
- AI and analytics: `azure-openai`, `azure-cognitive-search` (label it `Azure AI
  Search`), `azure-databricks`, `azure-synapse`.
- Operations: `azure-monitor`, `azure-app-insights`, `azure-log-analytics`.
- A service with no kind yet: use the generic kind (`database`, `service`, `queue`)
  and the official name in `technology`.

## Naming
Official names: `Azure Cosmos DB` (not CosmosDB), `Microsoft Entra ID` (not Azure AD),
`Azure Kubernetes Service (AKS)`, `Azure OpenAI`, `Azure AI Search` (not Cognitive
Search). Label the node with its role when there are several of a service
(`Orders API`, technology `Azure Functions`), otherwise with the service name.

## Reference patterns
- **Web app + API + data**: Front Door (WAF) -> App Service (web) -> Functions or
  Container Apps (API) -> Azure SQL / Cosmos DB; Key Vault for secrets; Application
  Insights for telemetry.
- **Event-driven**: producer -> Event Grid (events) or Service Bus (commands) ->
  Functions consumers -> Cosmos DB; dead-letter queue shown dashed.
- **Data platform**: sources -> Data Factory -> ADLS Gen2 (bronze/silver/gold) ->
  Databricks or Synapse/Fabric -> Power BI.
- **AI / RAG app**: user -> App Service -> orchestrator (Functions/Container Apps) ->
  Azure AI Search (retrieve) + Azure OpenAI (generate); Blob Storage -> indexer ->
  AI Search for ingestion.

## Edge labels
`HTTPS`, `private endpoint`, `SQL`, `AMQP` (Service Bus), `events` (Event Grid),
`triggers`, `indexes`, `embeddings`, `managed identity` (dotted) for identity-based
access.

## Common mistakes
- Old names: Azure AD, Cognitive Search, Azure Container Service.
- Every PaaS drawn inside the VNet.
- Subscription, resource group and management group all drawn as nested boxes in a
  workload diagram.
- Arrows from Azure Monitor/Key Vault to every service; show one representative edge.
