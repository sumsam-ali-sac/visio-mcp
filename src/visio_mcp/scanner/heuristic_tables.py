"""Map IaC resource types to diagram kinds, roles and data-store families."""

from __future__ import annotations

from typing import NamedTuple


class Entry(NamedTuple):
    preferred: str  # provider-specific catalog kind (used when the catalog knows it)
    base: str  # generic fallback kind
    role: str  # compute | data | edge | aux
    label: str  # short technology label
    family: str | None = None  # data-store family shared with detected databases
    fkind: str = "database"  # database | cache | queue | storage


def _e(pref: str, base: str, role: str, label: str, family: str | None = None, fkind: str = "database") -> Entry:
    return Entry(pref, base, role, label, family, fkind)


_AWS_LAMBDA = _e("aws-lambda", "function", "compute", "Lambda")
_AWS_API = _e("aws-api-gateway", "gateway", "edge", "API Gateway")
_AWS_DDB = _e("dynamodb", "database", "data", "DynamoDB", "DynamoDB")
_AWS_S3 = _e("aws-s3", "storage", "data", "S3", "S3", "storage")
_AWS_SQS = _e("aws-sqs", "queue", "data", "SQS", "SQS", "queue")
_AWS_SNS = _e("topic", "queue", "data", "SNS", "SNS", "queue")
_AWS_RDS = _e("aws-rds", "database", "data", "RDS")
_AWS_CACHE = _e("aws-elasticache", "cache", "data", "ElastiCache", "Redis", "cache")
_AWS_CDN = _e("cdn", "gateway", "edge", "CloudFront")
_AWS_LB = _e("aws-alb", "loadbalancer", "edge", "Load balancer")
_AWS_ECS = _e("container", "service", "compute", "ECS")
_AWS_COGNITO = _e("identity", "service", "aux", "Cognito")

_AZ_FUNC = _e("azure-functions", "function", "compute", "Function App")
_AZ_WEB = _e("azure-app-service", "webapp", "compute", "App Service")
_AZ_STORAGE = _e("azure-storage", "storage", "data", "Storage", "Azure Blob Storage", "storage")
_AZ_SQL = _e("azure-sql", "database", "data", "Azure SQL", "SQL Server")
_AZ_PG = _e("azure-postgresql", "database", "data", "PostgreSQL", "PostgreSQL")
_AZ_MYSQL = _e("azure-mysql", "database", "data", "MySQL", "MySQL")
_AZ_COSMOS = _e("cosmos-db", "database", "data", "Cosmos DB", "Cosmos DB")
_AZ_REDIS = _e("azure-redis", "cache", "data", "Redis Cache", "Redis", "cache")
_AZ_SB = _e("azure-service-bus", "queue", "data", "Service Bus", "Azure Service Bus", "queue")
_AZ_EH = _e("event-hubs", "queue", "data", "Event Hubs", "Event Hubs", "queue")
_AZ_KV = _e("key-vault", "service", "aux", "Key Vault")
_AZ_CA = _e("container", "service", "compute", "Container App")
_AZ_AKS = _e("aks", "service", "compute", "AKS")
_AZ_AGW = _e("azure-app-gateway", "gateway", "edge", "App Gateway")
_AZ_APIM = _e("azure-apim", "gateway", "edge", "API Management")
_AZ_CDN = _e("cdn", "gateway", "edge", "Front Door")
_AZ_LB = _e("loadbalancer", "loadbalancer", "edge", "Load Balancer")

_GCP_RUN = _e("gcp-cloud-run", "service", "compute", "Cloud Run")
_GCP_FUNC = _e("gcp-functions", "function", "compute", "Cloud Function")
_GCP_SQL = _e("gcp-cloud-sql", "database", "data", "Cloud SQL")
_GCP_GCS = _e("gcp-storage", "storage", "data", "Cloud Storage", "Cloud Storage", "storage")
_GCP_PUBSUB = _e("gcp-pubsub", "queue", "data", "Pub/Sub", "Pub/Sub", "queue")
_GCP_BQ = _e("gcp-bigquery", "database", "data", "BigQuery", "BigQuery")
_GCP_GKE = _e("gcp-gke", "service", "compute", "GKE")
_GCP_REDIS = _e("cache", "cache", "data", "Memorystore", "Redis", "cache")

RES_TABLE: dict[str, Entry] = {
    # Terraform - AWS
    "aws_lambda_function": _AWS_LAMBDA,
    "aws_api_gateway_rest_api": _AWS_API,
    "aws_apigatewayv2_api": _AWS_API,
    "aws_dynamodb_table": _AWS_DDB,
    "aws_s3_bucket": _AWS_S3,
    "aws_sqs_queue": _AWS_SQS,
    "aws_sns_topic": _AWS_SNS,
    "aws_db_instance": _AWS_RDS,
    "aws_rds_cluster": _AWS_RDS,
    "aws_elasticache_cluster": _AWS_CACHE,
    "aws_elasticache_replication_group": _AWS_CACHE,
    "aws_cloudfront_distribution": _AWS_CDN,
    "aws_lb": _AWS_LB,
    "aws_alb": _AWS_LB,
    "aws_ecs_service": _AWS_ECS,
    "aws_eks_cluster": _e("aws-eks", "service", "compute", "EKS"),
    "aws_instance": _e("aws-ec2", "server", "compute", "EC2"),
    "aws_cognito_user_pool": _AWS_COGNITO,
    "aws_kinesis_stream": _e("queue", "queue", "data", "Kinesis", "Kinesis", "queue"),
    # CloudFormation / SAM / CDK
    "aws::lambda::function": _AWS_LAMBDA,
    "aws::serverless::function": _AWS_LAMBDA,
    "aws::apigateway::restapi": _AWS_API,
    "aws::apigatewayv2::api": _AWS_API,
    "aws::serverless::api": _AWS_API,
    "aws::serverless::httpapi": _AWS_API,
    "aws::dynamodb::table": _AWS_DDB,
    "aws::serverless::simpletable": _AWS_DDB,
    "aws::s3::bucket": _AWS_S3,
    "aws::sqs::queue": _AWS_SQS,
    "aws::sns::topic": _AWS_SNS,
    "aws::rds::dbinstance": _AWS_RDS,
    "aws::rds::dbcluster": _AWS_RDS,
    "aws::elasticache::cachecluster": _AWS_CACHE,
    "aws::cloudfront::distribution": _AWS_CDN,
    "aws::ecs::service": _AWS_ECS,
    "aws::elasticloadbalancingv2::loadbalancer": _AWS_LB,
    "aws::cognito::userpool": _AWS_COGNITO,
    # Terraform - Azure
    "azurerm_linux_function_app": _AZ_FUNC,
    "azurerm_windows_function_app": _AZ_FUNC,
    "azurerm_function_app": _AZ_FUNC,
    "azurerm_linux_web_app": _AZ_WEB,
    "azurerm_windows_web_app": _AZ_WEB,
    "azurerm_app_service": _AZ_WEB,
    "azurerm_static_web_app": _AZ_WEB,
    "azurerm_storage_account": _AZ_STORAGE,
    "azurerm_mssql_server": _AZ_SQL,
    "azurerm_mssql_database": _AZ_SQL,
    "azurerm_postgresql_flexible_server": _AZ_PG,
    "azurerm_postgresql_server": _AZ_PG,
    "azurerm_mysql_flexible_server": _AZ_MYSQL,
    "azurerm_cosmosdb_account": _AZ_COSMOS,
    "azurerm_redis_cache": _AZ_REDIS,
    "azurerm_servicebus_namespace": _AZ_SB,
    "azurerm_servicebus_queue": _AZ_SB,
    "azurerm_servicebus_topic": _AZ_SB,
    "azurerm_eventhub_namespace": _AZ_EH,
    "azurerm_eventhub": _AZ_EH,
    "azurerm_key_vault": _AZ_KV,
    "azurerm_container_app": _AZ_CA,
    "azurerm_kubernetes_cluster": _AZ_AKS,
    "azurerm_application_gateway": _AZ_AGW,
    "azurerm_api_management": _AZ_APIM,
    "azurerm_cdn_profile": _AZ_CDN,
    "azurerm_cdn_frontdoor_profile": _AZ_CDN,
    "azurerm_frontdoor": _AZ_CDN,
    "azurerm_lb": _AZ_LB,
    # Bicep / ARM
    "microsoft.web/sites": _AZ_WEB,
    "microsoft.web/sites:functionapp": _AZ_FUNC,
    "microsoft.web/staticsites": _AZ_WEB,
    "microsoft.storage/storageaccounts": _AZ_STORAGE,
    "microsoft.sql/servers": _AZ_SQL,
    "microsoft.sql/servers/databases": _AZ_SQL,
    "microsoft.dbforpostgresql/flexibleservers": _AZ_PG,
    "microsoft.dbformysql/flexibleservers": _AZ_MYSQL,
    "microsoft.documentdb/databaseaccounts": _AZ_COSMOS,
    "microsoft.cache/redis": _AZ_REDIS,
    "microsoft.servicebus/namespaces": _AZ_SB,
    "microsoft.servicebus/namespaces/queues": _AZ_SB,
    "microsoft.servicebus/namespaces/topics": _AZ_SB,
    "microsoft.eventhub/namespaces": _AZ_EH,
    "microsoft.keyvault/vaults": _AZ_KV,
    "microsoft.app/containerapps": _AZ_CA,
    "microsoft.containerservice/managedclusters": _AZ_AKS,
    "microsoft.network/applicationgateways": _AZ_AGW,
    "microsoft.apimanagement/service": _AZ_APIM,
    "microsoft.cdn/profiles": _AZ_CDN,
    "microsoft.network/frontdoors": _AZ_CDN,
    "microsoft.network/loadbalancers": _AZ_LB,
    # Terraform - GCP
    "google_cloud_run_service": _GCP_RUN,
    "google_cloud_run_v2_service": _GCP_RUN,
    "google_cloudfunctions_function": _GCP_FUNC,
    "google_cloudfunctions2_function": _GCP_FUNC,
    "google_sql_database_instance": _GCP_SQL,
    "google_storage_bucket": _GCP_GCS,
    "google_pubsub_topic": _GCP_PUBSUB,
    "google_bigquery_dataset": _GCP_BQ,
    "google_container_cluster": _GCP_GKE,
    "google_redis_instance": _GCP_REDIS,
    "google_compute_instance": _e("server", "server", "compute", "Compute Engine"),
    # Serverless Framework functions
    "serverless::function:aws": _AWS_LAMBDA,
    "serverless::function:azure": _AZ_FUNC,
    "serverless::function:gcp": _GCP_FUNC,
}

# A resource is dropped when its shadowing resource type exists in the same repo (avoid server + database twins).
SHADOWS: dict[str, str] = {
    "azurerm_mssql_server": "azurerm_mssql_database",
    "microsoft.sql/servers": "microsoft.sql/servers/databases",
    "azurerm_servicebus_queue": "azurerm_servicebus_namespace",
    "azurerm_servicebus_topic": "azurerm_servicebus_namespace",
    "microsoft.servicebus/namespaces/queues": "microsoft.servicebus/namespaces",
    "microsoft.servicebus/namespaces/topics": "microsoft.servicebus/namespaces",
    "azurerm_eventhub": "azurerm_eventhub_namespace",
}

PROVIDER_LABEL = {"azure": "Azure", "aws": "AWS", "gcp": "Google Cloud"}


def resource_key(res: dict) -> str:
    t = str(res.get("type", ""))
    if res.get("iac") == "serverless" and t == "serverless::function":
        return f"serverless::function:{res.get('provider', 'aws')}"
    low = t.lower()
    if low == "microsoft.web/sites" and res.get("hint") == "functionapp":
        return "microsoft.web/sites:functionapp"
    return low


def lookup_resource(res: dict) -> Entry | None:
    return RES_TABLE.get(resource_key(res))


def _engine_family(hint: str) -> str | None:
    h = hint.lower()
    if "postgres" in h:
        return "PostgreSQL"
    if "mysql" in h or "maria" in h:
        return "MySQL"
    if "sqlserver" in h or "sql-server" in h:
        return "SQL Server"
    return None


def resource_family(res: dict) -> tuple[str, str] | None:
    """(fkind, family label) when the resource is a data store that matches a detected-database family."""
    entry = lookup_resource(res)
    if entry is None or entry.role != "data":
        return None
    if entry.family:
        return entry.fkind, entry.family
    fam = _engine_family(str(res.get("hint", "")))
    return ("database", fam) if fam else None
