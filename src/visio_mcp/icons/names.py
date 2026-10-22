"""Icon name normalization and the curated kind -> icon name table."""

from __future__ import annotations

import re
from pathlib import Path

from visio_mcp.icons.providers import IMAGE_EXTS

_PREFIXES = re.compile(
    r"^(?:\d+-icon-service-|icon-service-|arch-category-|arch-|res-|"
    r"aws-|amazon-|azure-|microsoft-|google-cloud-|google-|gcp-)+"
)
_SUFFIXES = re.compile(
    r"(?:-(?:(?:16|20|24|32|40|48|64|80|96|128|256|512)(?:x\d+|px)?|light|dark|color|colour|rgb|cmyk|"
    r"icon|logo|svg|png|bg|bw))+$"
)


def normalize(name: str) -> str:
    """Icon file name (or a kind slug) -> comparable key.

    '10029-icon-service-Function-Apps.svg' -> 'function-apps'
    'Arch_AWS-Lambda_64.svg' -> 'lambda',  'Arch_Amazon-DynamoDB_48@5x.png' -> 'dynamodb'
    'Cloud-Run-512-color-rgb.svg' -> 'cloud-run', 'cloud_run.svg' -> 'cloud-run'
    """
    stem = Path(name).name
    low = stem.lower()
    if low.endswith(IMAGE_EXTS):
        stem = stem[: -4]
    s = stem.lower()
    s = re.sub(r"@\d+x$", "", s)  # retina suffix
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    for _ in range(3):  # prefixes and suffixes can stack ('arch-amazon-x-64-light')
        s2 = _SUFFIXES.sub("", _PREFIXES.sub("", s)).strip("-")
        if s2 == s or not s2:
            break
        s = s2
    return s[:100]


def squash(key: str) -> str:
    return key.replace("-", "")


def tokens(key: str) -> set[str]:
    out = set()
    for t in key.split("-"):
        if not t:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


# Curated kind -> icon names, in priority order (normalized; both the official vendor packs'
# naming and the `diagrams` package's naming). find() falls back to fuzzy token overlap.
ICON_NAMES: dict[str, tuple[str, ...]] = {
    # Azure
    "azure-app-service": ("app-services", "app-service"),
    "azure-functions": ("function-apps", "functions", "function-app"),
    "azure-aks": ("kubernetes-services", "kubernetes-service", "aks"),
    "azure-container-apps": ("container-apps", "worker-container-app", "container-apps-environments"),
    "azure-vm": ("virtual-machine", "virtual-machines", "vm"),
    "azure-static-web-apps": ("static-apps", "static-web-apps"),
    "azure-logic-apps": ("logic-apps",),
    "azure-sql-database": ("sql-database", "sql-databases", "sql-db"),
    "azure-cosmos-db": ("cosmos-db", "cosmosdb"),
    "azure-redis": ("cache-redis", "cache-for-redis", "redis-cache", "redis"),
    "azure-storage-account": ("storage-accounts", "storage-account"),
    "azure-blob-storage": ("storage-accounts", "blob-storage", "blob-block"),  # the modern storage icon
    "azure-ai-search": ("ai-search", "cognitive-search", "search-services", "search"),
    "azure-machine-learning": ("machine-learning", "machine-learning-studio-workspaces",
                               "machine-learning-service-workspaces"),
    "azure-private-endpoint": ("private-endpoints", "private-endpoint"),
    "azure-synapse": ("synapse-analytics", "synapse"),
    "azure-databricks": ("databricks",),
    "azure-data-factory": ("data-factories", "data-factory"),
    "azure-service-bus": ("service-bus",),
    "azure-event-hubs": ("event-hubs",),
    "azure-event-grid": ("event-grid-topics", "event-grid", "event-grid-domains"),
    "azure-api-management": ("api-management-services", "api-management"),
    "azure-front-door": ("front-door-and-cdn-profiles", "front-doors", "front-door"),
    "azure-application-gateway": ("application-gateways", "application-gateway"),
    "azure-load-balancer": ("load-balancers", "load-balancer"),
    "azure-vnet": ("virtual-networks", "virtual-network"),
    "azure-dns": ("dns-zones", "dns"),
    "azure-cdn": ("cdn-profiles", "cdn"),
    "azure-firewall": ("firewalls", "firewall"),
    "azure-bastion": ("bastions", "bastion"),
    "azure-key-vault": ("key-vaults", "key-vault"),
    "azure-entra-id": ("entra-id", "active-directory", "entra-id-protection"),
    "azure-monitor": ("monitor",),
    "azure-app-insights": ("application-insights",),
    "azure-log-analytics": ("log-analytics-workspaces", "log-analytics"),
    "azure-openai": ("openai", "azure-openai"),
    "azure-container-registry": ("container-registries", "container-registry"),
    # AWS
    "aws-ec2": ("ec2",),
    "aws-lambda": ("lambda",),
    "aws-ecs": ("elastic-container-service", "ecs"),
    "aws-eks": ("elastic-kubernetes-service", "eks"),
    "aws-fargate": ("fargate",),
    "aws-s3": ("simple-storage-service", "simple-storage-service-s3", "s3"),
    "aws-rds": ("rds",),
    "aws-aurora": ("aurora",),
    "aws-dynamodb": ("dynamodb",),
    "aws-elasticache": ("elasticache",),
    "aws-redshift": ("redshift",),
    "aws-athena": ("athena",),
    "aws-glue": ("glue",),
    "aws-kinesis": ("kinesis", "kinesis-data-streams"),
    "aws-sqs": ("simple-queue-service", "simple-queue-service-sqs", "sqs"),
    "aws-sns": ("simple-notification-service", "simple-notification-service-sns", "sns"),
    "aws-eventbridge": ("eventbridge",),
    "aws-step-functions": ("step-functions",),
    "aws-api-gateway": ("api-gateway",),
    "aws-cloudfront": ("cloudfront",),
    "aws-route53": ("route-53", "route53"),
    "aws-alb": ("elastic-load-balancing", "elb-application-load-balancer", "elastic-load-balancing-application-load-balancer"),
    "aws-vpc": ("virtual-private-cloud", "vpc"),
    "aws-waf": ("waf",),
    "aws-nat-gateway": ("vpc-nat-gateway", "nat-gateway"),
    "aws-opensearch": ("opensearch-service", "elasticsearch-service", "opensearch"),
    "aws-iam": ("identity-and-access-management", "identity-and-access-management-iam", "iam"),
    "aws-cognito": ("cognito",),
    "aws-kms": ("key-management-service", "kms"),
    "aws-secrets-manager": ("secrets-manager",),
    "aws-cloudwatch": ("cloudwatch",),
    "aws-sagemaker": ("sagemaker-ai", "sagemaker"),
    "aws-bedrock": ("bedrock",),
    "aws-ecr": ("elastic-container-registry", "ec2-container-registry", "ecr"),
    # Google Cloud ('google-' and 'gcp-' are stripped by normalize)
    "gcp-compute-engine": ("compute-engine",),
    "gcp-cloud-run": ("cloud-run", "run"),
    "gcp-gke": ("kubernetes-engine", "gke"),
    "gcp-cloud-functions": ("cloud-functions", "functions"),
    "gcp-app-engine": ("app-engine",),
    "gcp-cloud-storage": ("cloud-storage", "storage"),
    "gcp-cloud-sql": ("cloud-sql", "sql"),
    "gcp-spanner": ("cloud-spanner", "spanner"),
    "gcp-firestore": ("firestore", "cloud-firestore"),
    "gcp-bigtable": ("cloud-bigtable", "bigtable"),
    "gcp-bigquery": ("bigquery",),
    "gcp-memorystore": ("memorystore", "cloud-memorystore"),
    "gcp-artifact-registry": ("artifact-registry", "container-registry"),
    "gcp-pubsub": ("pubsub", "pub-sub", "cloud-pubsub"),
    "gcp-eventarc": ("eventarc", "pubsub"),
    "gcp-alloydb": ("alloydb", "alloy-db", "cloud-sql", "sql"),
    "gcp-looker": ("looker",),
    "gcp-dataflow": ("dataflow", "cloud-dataflow"),
    "gcp-dataproc": ("dataproc", "cloud-dataproc"),
    "gcp-api-gateway": ("api-gateway", "cloud-api-gateway", "apigee"),
    "gcp-cloud-load-balancing": ("cloud-load-balancing", "load-balancing"),
    "gcp-cloud-cdn": ("cloud-cdn", "cdn"),
    "gcp-cloud-dns": ("cloud-dns", "dns"),
    "gcp-vpc": ("virtual-private-cloud", "vpc"),
    "gcp-iam": ("identity-and-access-management", "cloud-iam", "iam"),
    "gcp-secret-manager": ("secret-manager",),
    "gcp-cloud-armor": ("cloud-armor", "armor"),
    "gcp-cloud-monitoring": ("cloud-monitoring", "monitoring"),
    "gcp-cloud-logging": ("cloud-logging", "logging"),
    "gcp-vertex-ai": ("vertex-ai",),
    "gcp-cloud-build": ("cloud-build", "build"),
    "gcp-cloud-scheduler": ("cloud-scheduler", "scheduler"),
}

# Icons drawn for a kind that are a stand-in rather than the service itself (no official icon
# for it in the `diagrams` pack); reported so users know.
STAND_INS = {"gcp-eventarc", "gcp-alloydb"}
