"""Semantic shape kinds -> Visio stencil masters."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Shape:
    stencil: str  # built-in stencil file name, e.g. "BASFLO_U.VSSX"
    master: str  # universal master name (NameU), e.g. "Process"


@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    candidates: tuple[Shape, ...]  # tried in order; first available wins
    category: str = "generic"  # style.CATEGORIES: picks the theme style
    geometry: str = "rect"  # style.GEOMETRY_MIN key: how non-Visio renderers draw it
    provider: str | None = None  # 'azure' | 'aws' | 'gcp' for cloud service kinds
    base: str | None = None  # generic kind to fall back to when no provider master exists
    glyph: str = ""  # 1-3 chars drawn inside the tile when there is no real icon (e.g. 'λ', 'SQL')


@dataclass(frozen=True)
class Resolved:
    shape: Shape
    warning: str | None  # set when the kind is unknown or we fell back
    kind: Kind | None = None  # the resolved kind (None when unknown)
    icon: bool = False  # the master is an icon: keep its colors, label sits below it


FALLBACK = Shape("BASIC_U.VSSX", "Rectangle")

_BASFLO = "BASFLO_U.VSSX"
_BASIC = "BASIC_U.VSSX"
_NETSYM = "NETSYM_U.VSSX"
_SERVER = "SERVER_U.VSSX"
_COMPS = "COMPS_U.VSSX"
_ORGCH = "ORGCH_U.VSSX"
_PEOPLE = "PEOPLE_U.VSSX"
_AZ_ENT = "AZUREENTERPRISE_U.VSSX"
_AZ_GEN = "AZUREGENERAL_U.VSSX"

# Plain geometric stencils take the theme's fill/line/font; icon stencils keep their own colors.
_FILLABLE = {_BASFLO, _BASIC, _ORGCH, "DBCHEN_U.VSSX", "WEBSIT_U.VSSX", "ANNOT_U.VSSX"}

# Clean geometric masters (all verified on Visio 16 BASIC_U / BASFLO_U).
_RECT = (_BASIC, "Rectangle")
_RR = (_BASIC, "Rounded Rectangle")
_HEX = (_BASIC, "Hexagon")
_ELL = (_BASIC, "Ellipse")
_CIRCLE = (_BASIC, "Circle")
_CAN = (_BASIC, "Can")
_DB = (_BASFLO, "Database")
_PARA = (_BASIC, "Parallelogram")
_DIAMOND = (_BASIC, "Diamond")


def _g(name: str, description: str, category: str, geometry: str, glyph: str, *shapes: tuple[str, str]) -> Kind:
    """A generic kind."""
    return Kind(name, description, tuple(Shape(s, m) for s, m in shapes), category, geometry,
                None, None, glyph)


_KINDS: tuple[Kind, ...] = (
    # --- flowchart / terminals ---
    _g("start", "Entry point of a flow (rounded terminator).", "terminal", "terminator", "", (_BASFLO, "Start/End")),
    _g("end", "Exit point of a flow (rounded terminator).", "terminal", "terminator", "", (_BASFLO, "Start/End")),
    _g("initial", "State machine initial pseudo state (filled dot).", "terminal", "circle", "", _CIRCLE, _ELL),
    _g("final", "State machine final pseudo state.", "terminal", "circle", "", _CIRCLE, _ELL),
    _g("process", "A step or action in a flow.", "flow", "rect", "", (_BASFLO, "Process"), _RECT),
    _g("subprocess", "A predefined process that is detailed elsewhere.", "flow", "subprocess", "", (_BASFLO, "Subprocess"), _RECT),
    _g("data", "Input or output data (parallelogram).", "flow", "parallelogram", "", (_BASFLO, "Data"), _PARA),
    _g("document", "A document or report.", "flow", "document", "", (_BASFLO, "Document")),
    _g("manual", "A manual step done by a person.", "flow", "trapezoid", "", (_BASIC, "Trapezoid")),
    _g("state", "A state in a state machine (rounded).", "flow", "rounded", "", _RR),
    _g("decision", "A yes/no or branching question.", "decision", "decision", "", (_BASFLO, "Decision"), _DIAMOND),
    # --- software architecture (C4 style) ---
    _g("service", "A backend service or application component.", "compute", "rounded", "", _RR),
    _g("microservice", "A small independently deployable service.", "compute", "rounded", "", _RR),
    _g("component", "A component inside a container or application (C4 component).", "compute", "rounded", "", _RR),
    _g("container", "A deployable app or data container (C4 container, e.g. SPA, API, DB).", "compute", "rounded", "", _RR),
    _g("system", "A software system (C4 software system).", "compute", "rounded", "", _RR),
    _g("worker", "A background worker or job processor.", "compute", "rounded", "", _RR),
    _g("function", "A serverless function.", "compute", "rounded", "λ", _RR),
    _g("cron", "A scheduled job or scheduler (cron, timer).", "compute", "rounded", "", _RR),
    _g("cluster", "A container orchestration cluster such as Kubernetes.", "compute", "hexagon", "K8s", _HEX),
    _g("ml-model", "A machine-learning model or inference endpoint.", "compute", "hexagon", "ML", _HEX),
    _g("llm", "A large language model or AI assistant.", "compute", "hexagon", "AI", _HEX),
    _g("api", "An API or web service endpoint.", "integration", "hexagon", "", _HEX),
    _g("gateway", "An API gateway or protocol gateway.", "integration", "hexagon", "", _HEX),
    _g("queue", "A message queue or broker.", "integration", "queue", "", _PARA),
    _g("topic", "A pub/sub topic or event stream (Kafka, Event Hubs, Kinesis).", "integration", "queue", "", _PARA),
    _g("etl", "An ETL / data integration job or pipeline.", "integration", "hexagon", "ETL", _HEX),
    _g("email", "An email service (SMTP, transactional mail).", "integration", "rounded", "@", _RR),
    _g("notification", "A notification or push service (SMS, push, chat alerts).", "integration", "rounded", "", _RR),
    # --- data ---
    _g("database", "A database or data store (cylinder).", "data", "cylinder", "", _DB, (_NETSYM, "Relational database"), _CAN),
    _g("cache", "An in-memory cache such as Redis or Memcached.", "data", "cylinder", "", _CAN),
    _g("storage", "Object, blob or file storage.", "data", "cylinder", "", _CAN),
    _g("data-warehouse", "An analytical data warehouse.", "data", "cylinder", "DW", _CAN),
    _g("data-lake", "A data lake for raw and curated data.", "data", "cylinder", "", _CAN),
    _g("search", "A search index or engine (Elasticsearch, OpenSearch).", "data", "cylinder", "", _CAN),
    _g("vector-db", "A vector database for embeddings.", "data", "cylinder", "", _CAN),
    _g("repo", "A source code (git) repository.", "data", "rounded", "", _RR),
    _g("registry", "A container or package registry.", "data", "rounded", "", _RR),
    _g("artifact", "A build artifact or package.", "data", "rounded", "", _RR),
    # --- CI/CD ---
    _g("pipeline", "A CI/CD or data pipeline.", "flow", "rounded", "", _RR),
    _g("build", "A build step.", "flow", "rounded", "", _RR),
    _g("test", "A test or verification step.", "flow", "rounded", "", _RR),
    _g("deploy", "A deployment or release step.", "flow", "rounded", "", _RR),
    # --- clients / people / external ---
    _g("webapp", "A web app, website or frontend page.", "client", "rounded", "", _RR),
    _g("client", "A client application or browser.", "client", "icon", "", (_AZ_GEN, "Browser"), (_COMPS, "PC"), _RR),
    _g("mobile", "A mobile device or app.", "client", "icon", "", (_AZ_GEN, "Mobile"), (_AZ_ENT, "Phone"), (_COMPS, "PDA")),
    _g("pc", "A desktop or laptop computer.", "client", "icon", "", (_COMPS, "PC"), (_COMPS, "Laptop computer")),
    _g("user", "A person or actor using the system.", "person", "person", "", (_PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("person", "A person (C4 person).", "person", "person", "", (_PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("actor", "An actor interacting with the system (UML actor).", "person", "person", "", (_PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _g("external", "An external system or third-party service outside your control.", "external", "rect", "", _RECT),
    _g("external-system", "An external software system (C4 external system).", "external", "rect", "", _RECT),
    _g("payment", "A payment provider or gateway (Stripe, PayPal).", "external", "rounded", "$", _RR),
    # --- network / infrastructure / security ---
    _g("server", "A generic server.", "network", "icon", "", (_SERVER, "Server"), _RR),
    _g("router", "A network router.", "network", "icon", "", (_NETSYM, "Router"), _HEX),
    _g("switch", "A network switch.", "network", "icon", "", (_NETSYM, "Workgroup switch"), _HEX),
    _g("loadbalancer", "A load balancer spreading traffic across instances.", "network", "hexagon", "LB", _HEX),
    _g("cdn", "A content delivery network.", "network", "hexagon", "CDN", _HEX),
    _g("dns", "A DNS service or zone.", "network", "hexagon", "DNS", _HEX),
    _g("cloud", "A cloud or WAN network region.", "network", "cloud", "", ("NETLOC_U.VSSX", "Cloud"), (_AZ_ENT, "Cloud")),
    _g("internet", "The public internet.", "network", "cloud", "", (_AZ_ENT, "Internet"), ("AWSGEN_U.VSSX", "Internet alt1"), ("NETLOC_U.VSSX", "Cloud")),
    _g("firewall", "A firewall.", "security", "icon", "", (_AZ_ENT, "Firewall"), ("AWSGEN_U.VSSX", "Generic Firewall"), (_BASIC, "Pentagon")),
    _g("waf", "A web application firewall.", "security", "hexagon", "WAF", _HEX),
    _g("vpn", "A VPN gateway or tunnel.", "security", "hexagon", "VPN", _HEX),
    _g("identity", "An identity provider (IdP, SSO, directory).", "security", "rounded", "ID", _RR),
    _g("secrets", "A secrets manager or key vault.", "security", "rounded", "", _RR),
    # --- observability ---
    _g("monitoring", "Monitoring, metrics and alerting.", "generic", "rounded", "", _RR),
    _g("logging", "Log collection and analysis.", "generic", "rounded", "", _RR),
    # --- org chart ---
    _g("executive", "A top executive in an org chart.", "org", "rect", "", (_ORGCH, "Executive"), _RECT),
    _g("manager", "A manager in an org chart.", "org", "rect", "", (_ORGCH, "Manager"), _RECT),
    _g("position", "An employee or position in an org chart.", "org", "rect", "", (_ORGCH, "Position"), _RECT),
    # --- ERD ---
    # Chen entity is one shape; the Crow's Foot entity spawns attribute-row shapes that layout scatters.
    _g("entity", "A database entity (table) in an ER diagram.", "entity", "entity", "", ("DBCHEN_U.VSSX", "Entity"), _RECT),
    # --- generic ---
    _g("box", "A plain rectangle.", "generic", "rect", "", _RECT),
    _g("ellipse", "A plain ellipse.", "generic", "ellipse", "", _ELL),
    _g("mindmap-root", "The central topic of a mind map.", "generic", "ellipse", "", _ELL),
    _g("note", "A sticky note or free text annotation.", "note", "note", "", (_BASIC, "Single Snip Corner Rectangle"), ("ANNOT_U.VSSX", "Note symbol")),
)

# --- Cloud service kinds ------------------------------------------------------------------
# Stencil names: VERIFIED on a real Visio 16 install (kept from the original catalog, listed first):
#   AZUREENTERPRISE_U 'Storage'/'Firewall'/'Load Balancer'/'XML Web Service'/'Queue, General',
#   AZUREGENERAL_U 'Cache'/'Storage Queue', AZURECOMPUTE_U 'Function Apps', AZURECLOUD_U 'Azure Functions',
#   AWSDB_U 'Cache Node', AWSSTORAGE_U 'Storage', AWSGEN_U 'Generic Firewall'.
# All other master names are GUESSES, not verified (research only confirmed stencil categories: Microsoft
# Support "Create Azure diagrams in Visio" / "Create AWS diagrams in Visio" list Azure Compute/Databases/General/
# Networking/Storage and AWS Compute/Database/Networking Content Delivery/Storage; a third-party page names
# AZURESTORAGE_U.VSSX and AWSSTORAGE_U.VSSX). The resolver only tests availability, so a wrong guess is harmless:
# it falls through to `base`. Visio ships no GCP stencils, so GCP kinds have no candidates and use `base`.
_AZ = "azure"
_AWS = "aws"
_GCP = "gcp"


def _c(provider: str, slug: str, description: str, category: str, glyph: str, base: str,
       *shapes: tuple[str, str]) -> Kind:
    return Kind(f"{provider}-{slug}", description, tuple(Shape(s, m) for s, m in shapes), category, "icon",
                provider, base, glyph)


_CLOUD_KINDS: tuple[Kind, ...] = (
    # Azure
    _c(_AZ, "app-service", "Azure App Service web app.", "compute", "App", "webapp", ("AZURECOMPUTE_U.VSSX", "App Services")),
    _c(_AZ, "functions", "Azure Functions (serverless).", "compute", "λ", "function", ("AZURECOMPUTE_U.VSSX", "Function Apps"), ("AZURECLOUD_U.VSSX", "Azure Functions")),
    _c(_AZ, "aks", "Azure Kubernetes Service.", "compute", "K8s", "cluster", ("AZURECOMPUTE_U.VSSX", "Kubernetes Services")),
    _c(_AZ, "container-apps", "Azure Container Apps.", "compute", "CA", "container", ("AZURECOMPUTE_U.VSSX", "Container Apps")),
    _c(_AZ, "vm", "Azure Virtual Machine.", "compute", "VM", "server", ("AZURECOMPUTE_U.VSSX", "Virtual Machine")),
    _c(_AZ, "static-web-apps", "Azure Static Web Apps.", "client", "SWA", "webapp", ("AZURECOMPUTE_U.VSSX", "Static Web Apps")),
    _c(_AZ, "logic-apps", "Azure Logic Apps workflows.", "integration", "LA", "service", ("AZURECOMPUTE_U.VSSX", "Logic Apps")),
    _c(_AZ, "sql-database", "Azure SQL Database.", "data", "SQL", "database", ("AZUREDATABASES_U.VSSX", "SQL Database")),
    _c(_AZ, "cosmos-db", "Azure Cosmos DB.", "data", "Cos", "database", ("AZUREDATABASES_U.VSSX", "Azure Cosmos DB")),
    _c(_AZ, "redis", "Azure Cache for Redis.", "data", "Rds", "cache", (_AZ_GEN, "Cache")),
    _c(_AZ, "storage-account", "Azure Storage account (blob, files).", "data", "Stg", "storage", (_AZ_ENT, "Storage"), ("AZURESTORAGE_U.VSSX", "Storage Accounts")),
    _c(_AZ, "blob-storage", "Azure Blob Storage.", "data", "Blob", "storage", ("AZURESTORAGE_U.VSSX", "Blob Storage"), (_AZ_ENT, "Storage")),
    _c(_AZ, "ai-search", "Azure AI Search (formerly Cognitive Search).", "data", "AIS", "search",
       ("AZUREAI_U.VSSX", "Cognitive Search")),
    _c(_AZ, "machine-learning", "Azure Machine Learning workspace.", "compute", "ML", "ml-model"),
    _c(_AZ, "private-endpoint", "Azure Private Endpoint.", "network", "PE", "gateway"),
    _c(_AZ, "synapse", "Azure Synapse Analytics.", "data", "Syn", "data-warehouse", ("AZUREDATABASES_U.VSSX", "Synapse Analytics")),
    _c(_AZ, "databricks", "Azure Databricks.", "compute", "DBX", "etl", ("AZUREANALYTICS_U.VSSX", "Azure Databricks")),
    _c(_AZ, "data-factory", "Azure Data Factory.", "integration", "ADF", "etl", ("AZUREANALYTICS_U.VSSX", "Data Factory")),
    _c(_AZ, "service-bus", "Azure Service Bus.", "integration", "SB", "queue", (_AZ_ENT, "Queue, General"), (_AZ_GEN, "Storage Queue")),
    _c(_AZ, "event-hubs", "Azure Event Hubs.", "integration", "EH", "topic", ("AZUREINTEGRATION_U.VSSX", "Event Hubs")),
    _c(_AZ, "event-grid", "Azure Event Grid.", "integration", "EG", "topic", ("AZUREINTEGRATION_U.VSSX", "Event Grid")),
    _c(_AZ, "api-management", "Azure API Management.", "integration", "APIM", "gateway", ("AZUREINTEGRATION_U.VSSX", "API Management"), (_AZ_ENT, "XML Web Service")),
    _c(_AZ, "front-door", "Azure Front Door.", "network", "FD", "cdn", ("AZURENETWORKING_U.VSSX", "Front Doors")),
    _c(_AZ, "application-gateway", "Azure Application Gateway.", "network", "AGW", "loadbalancer", ("AZURENETWORKING_U.VSSX", "Application Gateways")),
    _c(_AZ, "load-balancer", "Azure Load Balancer.", "network", "LB", "loadbalancer", (_AZ_ENT, "Load Balancer")),
    _c(_AZ, "vnet", "Azure Virtual Network.", "network", "VNet", "cloud", ("AZURENETWORKING_U.VSSX", "Virtual Networks")),
    _c(_AZ, "dns", "Azure DNS.", "network", "DNS", "dns", ("AZURENETWORKING_U.VSSX", "DNS Zones")),
    _c(_AZ, "cdn", "Azure CDN.", "network", "CDN", "cdn", ("AZURENETWORKING_U.VSSX", "CDN Profiles")),
    _c(_AZ, "firewall", "Azure Firewall.", "security", "FW", "firewall", (_AZ_ENT, "Firewall"), ("AZURENETWORKING_U.VSSX", "Firewalls")),
    _c(_AZ, "bastion", "Azure Bastion.", "security", "Bas", "server", ("AZURENETWORKING_U.VSSX", "Bastions")),
    _c(_AZ, "key-vault", "Azure Key Vault.", "security", "KV", "secrets", ("AZURESECURITY_U.VSSX", "Key Vaults")),
    _c(_AZ, "entra-id", "Microsoft Entra ID (Azure AD).", "security", "ID", "identity", ("AZUREIDENTITY_U.VSSX", "Azure Active Directory")),
    _c(_AZ, "monitor", "Azure Monitor.", "generic", "Mon", "monitoring", ("AZUREMANAGEMENT_U.VSSX", "Monitor")),
    _c(_AZ, "app-insights", "Application Insights.", "generic", "AI", "monitoring", ("AZUREMANAGEMENT_U.VSSX", "Application Insights")),
    _c(_AZ, "log-analytics", "Log Analytics workspace.", "generic", "LA", "logging", ("AZUREMANAGEMENT_U.VSSX", "Log Analytics Workspaces")),
    _c(_AZ, "openai", "Azure OpenAI Service.", "compute", "AOAI", "llm", ("AZUREAI_U.VSSX", "Azure OpenAI")),
    _c(_AZ, "container-registry", "Azure Container Registry.", "data", "ACR", "registry", ("AZURECOMPUTE_U.VSSX", "Container Registries")),
    # AWS
    _c(_AWS, "ec2", "Amazon EC2 instance.", "compute", "EC2", "server", ("AWSCOMPUTE_U.VSSX", "Amazon EC2"), ("AWSCOMPUTE_U.VSSX", "Instance")),
    _c(_AWS, "lambda", "AWS Lambda function.", "compute", "λ", "function", ("AWSCOMPUTE_U.VSSX", "AWS Lambda"), ("AWSCOMPUTE_U.VSSX", "Lambda")),
    _c(_AWS, "ecs", "Amazon ECS.", "compute", "ECS", "container", ("AWSCOMPUTE_U.VSSX", "Amazon ECS")),
    _c(_AWS, "eks", "Amazon EKS (Kubernetes).", "compute", "K8s", "cluster", ("AWSCOMPUTE_U.VSSX", "Amazon EKS")),
    _c(_AWS, "fargate", "AWS Fargate.", "compute", "Fg", "container", ("AWSCOMPUTE_U.VSSX", "AWS Fargate")),
    _c(_AWS, "s3", "Amazon S3 bucket.", "data", "S3", "storage", ("AWSSTORAGE_U.VSSX", "Amazon S3"), ("AWSSTORAGE_U.VSSX", "Storage")),
    _c(_AWS, "rds", "Amazon RDS.", "data", "RDS", "database", ("AWSDB_U.VSSX", "Amazon RDS"), ("AWSDB_U.VSSX", "RDS")),
    _c(_AWS, "aurora", "Amazon Aurora.", "data", "Aur", "database", ("AWSDB_U.VSSX", "Amazon Aurora")),
    _c(_AWS, "dynamodb", "Amazon DynamoDB.", "data", "DDB", "database", ("AWSDB_U.VSSX", "Amazon DynamoDB"), ("AWSDB_U.VSSX", "DynamoDB")),
    _c(_AWS, "elasticache", "Amazon ElastiCache.", "data", "EC", "cache", ("AWSDB_U.VSSX", "Cache Node"), ("AWSDB_U.VSSX", "Amazon ElastiCache")),
    _c(_AWS, "redshift", "Amazon Redshift.", "data", "RS", "data-warehouse", ("AWSDB_U.VSSX", "Amazon Redshift")),
    _c(_AWS, "athena", "Amazon Athena.", "data", "Ath", "data-warehouse", ("AWSANALYTICS_U.VSSX", "Amazon Athena")),
    _c(_AWS, "glue", "AWS Glue ETL.", "integration", "Glue", "etl", ("AWSANALYTICS_U.VSSX", "AWS Glue")),
    _c(_AWS, "kinesis", "Amazon Kinesis stream.", "integration", "Kin", "topic", ("AWSANALYTICS_U.VSSX", "Amazon Kinesis")),
    _c(_AWS, "sqs", "Amazon SQS queue.", "integration", "SQS", "queue", ("AWSAPPINTEGRATION_U.VSSX", "Amazon SQS")),
    _c(_AWS, "sns", "Amazon SNS topic.", "integration", "SNS", "topic", ("AWSAPPINTEGRATION_U.VSSX", "Amazon SNS")),
    _c(_AWS, "eventbridge", "Amazon EventBridge.", "integration", "EB", "topic", ("AWSAPPINTEGRATION_U.VSSX", "Amazon EventBridge")),
    _c(_AWS, "step-functions", "AWS Step Functions.", "integration", "SFn", "pipeline", ("AWSAPPINTEGRATION_U.VSSX", "AWS Step Functions")),
    _c(_AWS, "api-gateway", "Amazon API Gateway.", "integration", "APIGW", "gateway", ("AWSNETWORK_U.VSSX", "Amazon API Gateway")),
    _c(_AWS, "cloudfront", "Amazon CloudFront CDN.", "network", "CF", "cdn", ("AWSNETWORK_U.VSSX", "Amazon CloudFront")),
    _c(_AWS, "route53", "Amazon Route 53 DNS.", "network", "R53", "dns", ("AWSNETWORK_U.VSSX", "Amazon Route 53")),
    _c(_AWS, "alb", "Application / Elastic Load Balancer.", "network", "ALB", "loadbalancer", ("AWSNETWORK_U.VSSX", "Elastic Load Balancing")),
    _c(_AWS, "vpc", "Amazon VPC.", "network", "VPC", "cloud", ("AWSNETWORK_U.VSSX", "Amazon VPC")),
    _c(_AWS, "waf", "AWS WAF.", "security", "WAF", "waf", ("AWSSECURITY_U.VSSX", "AWS WAF")),
    _c(_AWS, "nat-gateway", "AWS NAT gateway.", "network", "NAT", "gateway"),
    _c(_AWS, "opensearch", "Amazon OpenSearch Service.", "data", "OS", "search"),
    _c(_AWS, "iam", "AWS IAM.", "security", "IAM", "identity", ("AWSSECURITY_U.VSSX", "AWS IAM")),
    _c(_AWS, "cognito", "Amazon Cognito.", "security", "Cog", "identity", ("AWSSECURITY_U.VSSX", "Amazon Cognito")),
    _c(_AWS, "kms", "AWS KMS.", "security", "KMS", "secrets", ("AWSSECURITY_U.VSSX", "AWS KMS")),
    _c(_AWS, "secrets-manager", "AWS Secrets Manager.", "security", "SM", "secrets", ("AWSSECURITY_U.VSSX", "AWS Secrets Manager")),
    _c(_AWS, "cloudwatch", "Amazon CloudWatch.", "generic", "CW", "monitoring", ("AWSMANAGEMENT_U.VSSX", "Amazon CloudWatch")),
    _c(_AWS, "sagemaker", "Amazon SageMaker.", "compute", "SM", "ml-model", ("AWSML_U.VSSX", "Amazon SageMaker")),
    _c(_AWS, "bedrock", "Amazon Bedrock.", "compute", "Bed", "llm", ("AWSML_U.VSSX", "Amazon Bedrock")),
    _c(_AWS, "ecr", "Amazon ECR.", "data", "ECR", "registry", ("AWSCOMPUTE_U.VSSX", "Amazon ECR")),
    # GCP (no Visio stencils: rendered from `base` with the provider glyph tile)
    _c(_GCP, "compute-engine", "Google Compute Engine VM.", "compute", "GCE", "server"),
    _c(_GCP, "cloud-run", "Google Cloud Run.", "compute", "Run", "container"),
    _c(_GCP, "gke", "Google Kubernetes Engine.", "compute", "K8s", "cluster"),
    _c(_GCP, "cloud-functions", "Google Cloud Functions.", "compute", "λ", "function"),
    _c(_GCP, "app-engine", "Google App Engine.", "compute", "GAE", "webapp"),
    _c(_GCP, "cloud-storage", "Google Cloud Storage.", "data", "GCS", "storage"),
    _c(_GCP, "cloud-sql", "Google Cloud SQL.", "data", "SQL", "database"),
    _c(_GCP, "spanner", "Google Cloud Spanner.", "data", "Spn", "database"),
    _c(_GCP, "firestore", "Google Firestore.", "data", "FS", "database"),
    _c(_GCP, "bigtable", "Google Cloud Bigtable.", "data", "BT", "database"),
    _c(_GCP, "bigquery", "Google BigQuery.", "data", "BQ", "data-warehouse"),
    _c(_GCP, "memorystore", "Google Memorystore (Redis).", "data", "Mem", "cache"),
    _c(_GCP, "artifact-registry", "Google Artifact Registry.", "data", "AR", "registry"),
    _c(_GCP, "pubsub", "Google Pub/Sub.", "integration", "P/S", "topic"),
    _c(_GCP, "eventarc", "Google Eventarc event routing.", "integration", "EA", "topic"),
    _c(_GCP, "alloydb", "Google AlloyDB for PostgreSQL.", "data", "ADB", "database"),
    _c(_GCP, "looker", "Looker BI.", "client", "LK", "webapp"),
    _c(_GCP, "dataflow", "Google Dataflow.", "integration", "DF", "etl"),
    _c(_GCP, "dataproc", "Google Dataproc.", "compute", "DP", "etl"),
    _c(_GCP, "api-gateway", "Google API Gateway.", "integration", "APIGW", "gateway"),
    _c(_GCP, "cloud-load-balancing", "Google Cloud Load Balancing.", "network", "LB", "loadbalancer"),
    _c(_GCP, "cloud-cdn", "Google Cloud CDN.", "network", "CDN", "cdn"),
    _c(_GCP, "cloud-dns", "Google Cloud DNS.", "network", "DNS", "dns"),
    _c(_GCP, "vpc", "Google VPC network.", "network", "VPC", "cloud"),
    _c(_GCP, "iam", "Google Cloud IAM.", "security", "IAM", "identity"),
    _c(_GCP, "secret-manager", "Google Secret Manager.", "security", "SM", "secrets"),
    _c(_GCP, "cloud-armor", "Google Cloud Armor (WAF).", "security", "Arm", "waf"),
    _c(_GCP, "cloud-monitoring", "Google Cloud Monitoring.", "generic", "Mon", "monitoring"),
    _c(_GCP, "cloud-logging", "Google Cloud Logging.", "generic", "Log", "logging"),
    _c(_GCP, "vertex-ai", "Google Vertex AI.", "compute", "VAI", "ml-model"),
    _c(_GCP, "cloud-build", "Google Cloud Build.", "flow", "CB", "build"),
    _c(_GCP, "cloud-scheduler", "Google Cloud Scheduler.", "compute", "Sch", "cron"),
)

_BY_NAME: dict[str, Kind] = {k.name: k for k in _KINDS + _CLOUD_KINDS}

_ALIASES = {
    "azure-cognitive-search": "azure-ai-search",
    "db": "database",
    "postgres": "database",
    "postgresql": "database",
    "mysql": "database",
    "mongodb": "database",
    "mongo": "database",
    "sql": "database",
    "nosql": "database",
    "redis": "cache",
    "memcached": "cache",
    "kafka": "topic",
    "event-stream": "topic",
    "eventstream": "topic",
    "pubsub": "topic",
    "rabbitmq": "queue",
    "bus": "queue",
    "terminator": "start",
    "io": "data",
    "input": "data",
    "output": "data",
    "initial-state": "initial",
    "final-state": "final",
    "frontend": "webapp",
    "web": "webapp",
    "website": "webapp",
    "browser": "client",
    "app": "service",
    "blob": "storage",
    "bucket": "storage",
    "lambda": "function",
    "serverless": "function",
    "lb": "loadbalancer",
    "load_balancer": "loadbalancer",
    "load-balancer": "loadbalancer",
    "scheduler": "cron",
    "kubernetes": "cluster",
    "k8s": "cluster",
    "datawarehouse": "data-warehouse",
    "warehouse": "data-warehouse",
    "datalake": "data-lake",
    "elasticsearch": "search",
    "opensearch": "search",
    "model": "ml-model",
    "vectordb": "vector-db",
    "idp": "identity",
    "sso": "identity",
    "vault": "secrets",
    "keyvault": "secrets",
    "key-vault": "secrets",
    "observability": "monitoring",
    "git": "repo",
    "repository": "repo",
    "ci": "pipeline",
    "cd": "pipeline",
    "release": "deploy",
    "package": "artifact",
    "mail": "email",
    "smtp": "email",
    "alert": "notification",
    "push": "notification",
    "stripe": "payment",
    "software-system": "system",
    "external_system": "external-system",
    "root": "mindmap-root",
    "laptop": "pc",
    "computer": "pc",
    "employee": "position",
    "table": "entity",
    "rectangle": "box",
    "text": "note",
    # cloud services by their well-known short names
    "ec2": "aws-ec2",
    "s3": "aws-s3",
    "rds": "aws-rds",
    "dynamodb": "aws-dynamodb",
    "sqs": "aws-sqs",
    "sns": "aws-sns",
    "cloudfront": "aws-cloudfront",
    "route53": "aws-route53",
    "bigquery": "gcp-bigquery",
    "gke": "gcp-gke",
    "cloud-run": "gcp-cloud-run",
    "cosmosdb": "azure-cosmos-db",
    "aks": "azure-aks",
    "blob-storage": "azure-blob-storage",
    "eks": "aws-eks",
}


def kinds() -> dict[str, Kind]:
    """All known kinds, keyed by name."""
    return dict(_BY_NAME)


def providers() -> tuple[str, ...]:
    """Cloud providers that have service kinds."""
    return tuple(sorted({k.provider for k in _BY_NAME.values() if k.provider}))


def kinds_by_category() -> dict[str, list[Kind]]:
    """Generic (non-provider) kinds grouped by style category, in catalog order."""
    out: dict[str, list[Kind]] = {}
    for k in _KINDS:
        out.setdefault(k.category, []).append(k)
    return out


def describe_kinds(provider: str | None = None) -> str:
    """Compact markdown listing of kinds for LLM prompts: generic by category, then a provider's cloud kinds."""
    lines = ["## Kinds (generic)"]
    for cat, ks in kinds_by_category().items():
        lines.append(f"- **{cat}**: " + "; ".join(f"`{k.name}` {k.description.rstrip('.')}" for k in ks))
    wanted = [p for p in providers() if provider is None or p == provider.strip().lower()]
    for p in wanted:
        lines.append(f"## Kinds ({p})")
        ks = [k for k in _CLOUD_KINDS if k.provider == p]
        lines.append("- " + "; ".join(f"`{k.name}` {k.description.rstrip('.')}" for k in ks))
    return "\n".join(lines)


def lookup(kind: str) -> Kind | None:
    """The Kind for a name or alias (exact, no fuzzy matching), or None when unknown."""
    key = kind.strip().lower()
    return _BY_NAME.get(_ALIASES.get(key, key))


def suggest(kind: str, n: int = 3) -> list[str]:
    """Close kind names for an unknown kind: prefix matches first, then difflib matches."""
    key = kind.strip().lower()
    names = list(_BY_NAME) + list(_ALIASES)
    out = [x for x in names if key and (x.startswith(key) or (len(key) >= 3 and key in x))]
    out += difflib.get_close_matches(key, names, n=n, cutoff=0.6)
    seen: list[str] = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:n]


def _pick(k: Kind, has_master: Callable[[str, str], bool], depth: int = 0) -> tuple[Shape, bool] | None:
    """First available master for k (own candidates, then its base chain) and whether it is an icon."""
    for shape in k.candidates:
        if has_master(shape.stencil, shape.master):
            return shape, shape.stencil not in _FILLABLE
    base = _BY_NAME.get(k.base) if k.base and depth < 8 else None
    return _pick(base, has_master, depth + 1) if base else None


def resolve(kind: str, has_master: Callable[[str, str], bool]) -> Resolved:
    """Pick the first available candidate for kind (then its base kind); else FALLBACK with a warning."""
    k = lookup(kind)
    if k is None:
        hint = suggest(kind)
        tip = f"; did you mean {', '.join(repr(h) for h in hint)}?" if hint else ""
        return Resolved(FALLBACK, f"unknown kind '{kind}', drew a rectangle{tip} (see list_kinds)")
    picked = _pick(k, has_master)
    if picked:
        shape, icon = picked
        return Resolved(shape, None, k, icon)
    return Resolved(FALLBACK, f"no stencil master available for kind '{kind}', drew a rectangle", k)
