"""Cloud service kinds (Azure, AWS, GCP) with their stencil master candidates."""

from __future__ import annotations

from visio_mcp.catalog.model import Kind, Shape
from visio_mcp.catalog.stencils import AZ_ENT, AZ_GEN

# Stencil names: VERIFIED on a real Visio 16 install:
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


CLOUD_KINDS: tuple[Kind, ...] = (
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
    _c(_AZ, "redis", "Azure Cache for Redis.", "data", "Rds", "cache", (AZ_GEN, "Cache")),
    _c(_AZ, "storage-account", "Azure Storage account (blob, files).", "data", "Stg", "storage", (AZ_ENT, "Storage"), ("AZURESTORAGE_U.VSSX", "Storage Accounts")),
    _c(_AZ, "blob-storage", "Azure Blob Storage.", "data", "Blob", "storage", ("AZURESTORAGE_U.VSSX", "Blob Storage"), (AZ_ENT, "Storage")),
    _c(_AZ, "ai-search", "Azure AI Search (formerly Cognitive Search).", "data", "AIS", "search",
       ("AZUREAI_U.VSSX", "Cognitive Search")),
    _c(_AZ, "machine-learning", "Azure Machine Learning workspace.", "compute", "ML", "ml-model"),
    _c(_AZ, "private-endpoint", "Azure Private Endpoint.", "network", "PE", "gateway"),
    _c(_AZ, "synapse", "Azure Synapse Analytics.", "data", "Syn", "data-warehouse", ("AZUREDATABASES_U.VSSX", "Synapse Analytics")),
    _c(_AZ, "databricks", "Azure Databricks.", "compute", "DBX", "etl", ("AZUREANALYTICS_U.VSSX", "Azure Databricks")),
    _c(_AZ, "data-factory", "Azure Data Factory.", "integration", "ADF", "etl", ("AZUREANALYTICS_U.VSSX", "Data Factory")),
    _c(_AZ, "service-bus", "Azure Service Bus.", "integration", "SB", "queue", (AZ_ENT, "Queue, General"), (AZ_GEN, "Storage Queue")),
    _c(_AZ, "event-hubs", "Azure Event Hubs.", "integration", "EH", "topic", ("AZUREINTEGRATION_U.VSSX", "Event Hubs")),
    _c(_AZ, "event-grid", "Azure Event Grid.", "integration", "EG", "topic", ("AZUREINTEGRATION_U.VSSX", "Event Grid")),
    _c(_AZ, "api-management", "Azure API Management.", "integration", "APIM", "gateway", ("AZUREINTEGRATION_U.VSSX", "API Management"), (AZ_ENT, "XML Web Service")),
    _c(_AZ, "front-door", "Azure Front Door.", "network", "FD", "cdn", ("AZURENETWORKING_U.VSSX", "Front Doors")),
    _c(_AZ, "application-gateway", "Azure Application Gateway.", "network", "AGW", "loadbalancer", ("AZURENETWORKING_U.VSSX", "Application Gateways")),
    _c(_AZ, "load-balancer", "Azure Load Balancer.", "network", "LB", "loadbalancer", (AZ_ENT, "Load Balancer")),
    _c(_AZ, "vnet", "Azure Virtual Network.", "network", "VNet", "cloud", ("AZURENETWORKING_U.VSSX", "Virtual Networks")),
    _c(_AZ, "dns", "Azure DNS.", "network", "DNS", "dns", ("AZURENETWORKING_U.VSSX", "DNS Zones")),
    _c(_AZ, "cdn", "Azure CDN.", "network", "CDN", "cdn", ("AZURENETWORKING_U.VSSX", "CDN Profiles")),
    _c(_AZ, "firewall", "Azure Firewall.", "security", "FW", "firewall", (AZ_ENT, "Firewall"), ("AZURENETWORKING_U.VSSX", "Firewalls")),
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
