"""Repository discovery and fast, deterministic profiling."""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from ._common import (
    GitIgnore,
    FileEntry,
    as_list,
    as_str_list,
    is_ignored_dir,
    normalize_path,
    parse_yaml,
    read_text,
    resolve_dir,
    walk,
    yaml_docs,
)
from .model import RepoInfo

# --------------------------------------------------------------------------- tables

_LANG = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".cs": "C#", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte", ".tf": "HCL", ".bicep": "Bicep", ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir", ".fs": "F#", ".vb": "VB.NET", ".lua": "Lua", ".r": "R",
}
_NON_PRIMARY = {"HTML", "CSS", "SQL", "Shell", "PowerShell", "HCL", "Bicep"}
_SAMPLE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php"}
_TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "mocks", "__mocks__", "fixtures", "examples",
               "docs", "testdata", "samples"}

_MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "gemfile", "composer.json", "pipfile",
}
_MANIFEST_EXT = {".csproj", ".fsproj", ".sln"}

_ENTRY_NAMES = {
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "server.py", "__main__.py", "run.py",
    "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts", "main.js", "main.ts",
    "program.cs", "startup.cs", "main.go", "main.rs", "main.java", "function_app.py", "lambda_function.py",
    "handler.py", "handler.js", "handler.ts", "main.kt",
}

# --- dependency signal tables ------------------------------------------------

_FRAMEWORKS: list[tuple[str, tuple[str, ...]]] = [
    ("FastAPI", ("fastapi",)),
    ("Django", ("django",)),
    ("Flask", ("flask",)),
    ("Celery", ("celery",)),
    ("Next.js", ("next",)),
    ("React", ("react", "react-dom")),
    ("Angular", ("@angular/core",)),
    ("Vue", ("vue",)),
    ("Nuxt", ("nuxt", "nuxt3")),
    ("Svelte", ("svelte", "@sveltejs/kit")),
    ("Remix", ("@remix-run/react", "@remix-run/node")),
    ("React Native", ("react-native",)),
    ("Electron", ("electron",)),
    ("NestJS", ("@nestjs/core",)),
    ("Express", ("express",)),
    ("Fastify", ("fastify",)),
    ("Spring Boot", ("spring-boot", "org.springframework.boot", "spring-boot-starter")),
    ("Quarkus", ("io.quarkus", "quarkus-resteasy")),
    ("ASP.NET Core", ("microsoft.aspnetcore", "sdk:microsoft.net.sdk.web")),
    (".NET Azure Functions", ("microsoft.azure.functions", "microsoft.net.sdk.functions", "microsoft.azure.webjobs")),
    ("Azure Functions", ("azure-functions", "@azure/functions")),
    ("AWS Lambda", ("aws-lambda-powertools", "@types/aws-lambda", "aws-lambda", "mangum", "serverless-http",
                    "amazon.lambda.core", "com.amazonaws:aws-lambda-java-core")),
    ("Gin", ("github.com/gin-gonic/gin",)),
    ("Echo", ("github.com/labstack/echo",)),
    ("Fiber", ("github.com/gofiber/fiber",)),
    ("Rails", ("rails",)),
    ("Laravel", ("laravel/framework",)),
    ("Symfony", ("symfony/framework-bundle",)),
    ("Actix", ("actix-web",)),
    ("Axum", ("axum",)),
]

_DATABASES: list[tuple[str, tuple[str, ...], str]] = [
    ("PostgreSQL", ("psycopg", "psycopg2", "psycopg2-binary", "psycopg-binary", "asyncpg", "pg", "pg-promise",
                    "postgres", "npgsql", "github.com/lib/pq", "github.com/jackc/pgx", "org.postgresql",
                    "tokio-postgres", "node-postgres"), r"postgres(?:ql)?(?:\+\w+)?://|jdbc:postgresql"),
    ("MySQL", ("mysqlclient", "pymysql", "mysql", "mysql2", "mysql-connector-python", "mysql-connector-java",
               "github.com/go-sql-driver/mysql", "pomelo.entityframeworkcore.mysql", "mysql-connector", "aiomysql"),
     r"mysql(?:\+\w+)?://|jdbc:mysql|jdbc:mariadb"),
    ("SQL Server", ("pymssql", "mssql", "tedious", "microsoft.data.sqlclient", "system.data.sqlclient",
                    "microsoft.entityframeworkcore.sqlserver", "com.microsoft.sqlserver", "mssql-jdbc",
                    "github.com/denisenkom/go-mssqldb", "github.com/microsoft/go-mssqldb"),
     r"jdbc:sqlserver|server=tcp:|\.database\.windows\.net|mssql\+"),
    ("MongoDB", ("pymongo", "motor", "mongoose", "mongodb", "mongoengine", "mongodb.driver",
                 "spring-boot-starter-data-mongodb", "go.mongodb.org/mongo-driver"), r"mongodb(?:\+srv)?://"),
    ("Redis", ("redis", "aioredis", "ioredis", "stackexchange.redis", "github.com/go-redis/redis",
               "github.com/redis/go-redis", "spring-boot-starter-data-redis", "jedis", "lettuce-core",
               "bullmq", "bull", "connect-redis", "django-redis", "microsoft.extensions.caching.stackexchangeredis"),
     r"rediss?://|redis_url|redis_host"),
    ("Cosmos DB", ("azure-cosmos", "@azure/cosmos", "microsoft.azure.cosmos", "microsoft.azure.documentdb",
                   "azure-spring-data-cosmos"), r"documents\.azure\.com|cosmos_endpoint"),
    ("DynamoDB", ("@aws-sdk/client-dynamodb", "@aws-sdk/lib-dynamodb", "awssdk.dynamodbv2", "pynamodb",
                  "dynamoose"), r"\bdynamodb\b"),
    ("SQLite", ("aiosqlite", "sqlite3", "better-sqlite3", "sqlite", "microsoft.data.sqlite",
                "microsoft.entityframeworkcore.sqlite", "github.com/mattn/go-sqlite3"), r"sqlite(?:3)?:///|sqlite3\.connect"),
    ("Elasticsearch", ("elasticsearch", "elasticsearch-dsl", "@elastic/elasticsearch", "elastic.clients.elasticsearch",
                       "opensearch-py", "@opensearch-project/opensearch", "spring-boot-starter-data-elasticsearch",
                       "github.com/elastic/go-elasticsearch"), r"elasticsearch_url|elastic_host"),
    ("Memcached", ("pymemcache", "memcached", "memjs", "enyim.caching"), r"memcached_"),
    ("Cassandra", ("cassandra-driver", "gocql", "cassandra-driver-core"), r"cassandra_"),
    ("Neo4j", ("neo4j", "neo4j-driver"), r"bolt://|neo4j://"),
    ("Firestore", ("google-cloud-firestore", "@google-cloud/firestore"), r"firestore"),
    ("BigQuery", ("google-cloud-bigquery", "@google-cloud/bigquery"), r"bigquery"),
    ("Snowflake", ("snowflake-connector-python", "snowflake-sdk", "snowflake-sqlalchemy"), r"snowflakecomputing\.com"),
]

_MESSAGING: list[tuple[str, tuple[str, ...], str]] = [
    ("Kafka", ("kafkajs", "kafka-python", "confluent-kafka", "aiokafka", "spring-kafka", "confluent.kafka",
               "github.com/segmentio/kafka-go", "github.com/shopify/sarama", "github.com/ibm/sarama",
               "org.apache.kafka", "kafka-clients", "node-rdkafka", "faust"), r"kafka_bootstrap|bootstrap\.servers|kafka_brokers"),
    ("RabbitMQ", ("pika", "aio-pika", "amqplib", "amqp-connection-manager", "rabbitmq.client", "spring-boot-starter-amqp",
                  "github.com/rabbitmq/amqp091-go", "github.com/streadway/amqp", "masstransit.rabbitmq"),
     r"amqps?://|rabbitmq_"),
    ("Azure Service Bus", ("azure-servicebus", "@azure/service-bus", "azure.messaging.servicebus",
                           "microsoft.azure.servicebus", "microsoft.azure.webjobs.extensions.servicebus",
                           "masstransit.azureservicebus"), r"servicebus\.windows\.net|servicebus_"),
    ("Event Hubs", ("azure-eventhub", "@azure/event-hubs", "azure.messaging.eventhubs", "microsoft.azure.eventhubs",
                    "microsoft.azure.webjobs.extensions.eventhubs"), r"eventhub"),
    ("SQS", ("@aws-sdk/client-sqs", "awssdk.sqs"), r"client\(\s*['\"]sqs['\"]|\bsqs_queue|sqs\.amazonaws\.com|queue_url"),
    ("SNS", ("@aws-sdk/client-sns", "awssdk.simplenotificationservice", "awssdk.sns"),
     r"client\(\s*['\"]sns['\"]|\bsns\.publish|topic_arn"),
    ("Pub/Sub", ("google-cloud-pubsub", "@google-cloud/pubsub", "cloud.google.com/go/pubsub",
                 "com.google.cloud:google-cloud-pubsub"), r"pubsub_topic"),
    ("NATS", ("nats-py", "nats", "github.com/nats-io/nats.go", "nats.client", "nats.net"), r"nats://"),
    ("Celery", ("celery",), r"celery_broker"),
]

_STORAGE: list[tuple[str, tuple[str, ...], str]] = [
    ("Azure Blob Storage", ("azure-storage-blob", "@azure/storage-blob", "azure.storage.blobs",
                            "microsoft.azure.storage.blob", "azure.storage.queues"), r"blob\.core\.windows\.net"),
    ("S3", ("@aws-sdk/client-s3", "awssdk.s3", "s3transfer", "aws-sdk-s3"), r"client\(\s*['\"]s3['\"]|resource\(\s*['\"]s3['\"]|\.s3\.amazonaws\.com"),
    ("Cloud Storage", ("google-cloud-storage", "@google-cloud/storage"), r"storage\.googleapis\.com"),
    ("MinIO", ("minio",), r"minio_"),
]

_EXTERNAL: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("Stripe", ("stripe", "stripe-node", "@stripe/stripe-js", "stripe.net"), ("STRIPE_",)),
    ("Twilio", ("twilio", "twilio.rest.api"), ("TWILIO_",)),
    ("SendGrid", ("sendgrid", "@sendgrid/mail", "sendgrid.net"), ("SENDGRID_",)),
    ("OpenAI", ("openai", "azure.ai.openai"), ("OPENAI_",)),
    ("Anthropic", ("anthropic", "@anthropic-ai/sdk"), ("ANTHROPIC_",)),
    ("Auth0", ("auth0", "@auth0/auth0-spa-js", "@auth0/nextjs-auth0", "auth0-python", "express-openid-connect",
               "auth0.aspnetcore.authentication"), ("AUTH0_",)),
    ("Okta", ("okta", "@okta/okta-sdk-nodejs", "@okta/okta-auth-js", "okta.sdk"), ("OKTA_",)),
    ("Slack", ("slack-sdk", "slack-bolt", "@slack/web-api", "@slack/bolt", "slackclient"), ("SLACK_",)),
    ("GitHub API", ("pygithub", "@octokit/rest", "octokit", "@octokit/core", "octokit.net"), ()),
    ("Sentry", ("sentry-sdk", "@sentry/node", "@sentry/react", "@sentry/browser", "@sentry/nextjs", "sentry.aspnetcore"),
     ("SENTRY_",)),
    ("Mailgun", ("mailgun", "mailgun.js", "mailgun-js", "mailgun.net"), ("MAILGUN_",)),
    ("PayPal", ("paypalrestsdk", "@paypal/checkout-server-sdk", "paypal.core", "paypal-rest-sdk"), ("PAYPAL_",)),
    ("Firebase", ("firebase-admin", "firebase"), ("FIREBASE_",)),
    ("Supabase", ("supabase", "@supabase/supabase-js"), ("SUPABASE_",)),
    ("Algolia", ("algoliasearch", "algolia.search"), ("ALGOLIA_",)),
    ("Datadog", ("ddtrace", "datadog", "dd-trace", "datadog-api-client", "datadog.trace"), ("DATADOG_", "DD_API_KEY")),
    ("Shopify", ("shopifyapi", "@shopify/shopify-api", "shopify"), ("SHOPIFY_",)),
    ("Plaid", ("plaid-python", "plaid"), ("PLAID_",)),
    ("Cloudinary", ("cloudinary",), ("CLOUDINARY_",)),
    ("Google Maps", ("googlemaps", "@googlemaps/google-maps-services-js"), ("GOOGLE_MAPS_",)),
    ("Segment", ("analytics-python", "analytics-node", "@segment/analytics-next"), ("SEGMENT_",)),
    ("LaunchDarkly", ("launchdarkly-server-sdk", "launchdarkly-node-server-sdk", "launchdarkly-js-client-sdk"),
     ("LAUNCHDARKLY_",)),
    ("PostHog", ("posthog", "posthog-node", "posthog-js"), ("POSTHOG_",)),
    ("Postmark", ("postmarker", "postmark", "postmark.net"), ("POSTMARK_",)),
    ("Hugging Face", ("huggingface-hub",), ("HUGGINGFACE_", "HF_TOKEN")),
]

_CLOUD_PREFIXES = {
    "azure": ("azure-", "@azure/", "azure.", "microsoft.azure", "com.azure", "msal", "azure:"),
    "aws": ("boto3", "botocore", "aws-sdk", "@aws-sdk/", "awssdk.", "aws-lambda", "software.amazon.awssdk",
            "github.com/aws/aws-sdk-go", "aws-cdk", "aws_cdk", "@aws-cdk/", "amazon."),
    "gcp": ("google-cloud-", "@google-cloud/", "google.cloud", "cloud.google.com/go", "firebase-admin",
            "com.google.cloud", "google-auth"),
}

_IMAGE_FAMILIES: list[tuple[str, str, str]] = [
    # regex on image basename, family label, role kind
    (r"mongo-express", "", "service"),
    (r"postgres|postgis|timescale|pgvector|supabase/postgres", "PostgreSQL", "database"),
    (r"mysql|mariadb", "MySQL", "database"),
    (r"mongo", "MongoDB", "database"),
    (r"redis|valkey|keydb|dragonfly", "Redis", "cache"),
    (r"memcached", "Memcached", "cache"),
    (r"mssql|sql-edge|azure-sql", "SQL Server", "database"),
    (r"elasticsearch|opensearch", "Elasticsearch", "database"),
    (r"cassandra|scylla", "Cassandra", "database"),
    (r"rabbitmq", "RabbitMQ", "queue"),
    (r"kafka|redpanda", "Kafka", "queue"),
    (r"nats", "NATS", "queue"),
    (r"minio", "MinIO", "storage"),
    (r"azurite", "Azure Blob Storage", "storage"),
    (r"nginx|traefik|haproxy|envoy|caddy", "", "gateway"),
]

_FAMILY_LISTS = {"database": "databases", "cache": "databases", "queue": "messaging", "storage": "storage"}

_IAC_PRETTY = {
    "terraform": "Terraform", "bicep": "Bicep", "arm": "ARM templates", "cloudformation": "CloudFormation",
    "sam": "AWS SAM", "cdk": "AWS CDK", "serverless": "Serverless Framework", "pulumi": "Pulumi",
    "kubernetes": "Kubernetes", "helm": "Helm", "docker-compose": "Docker Compose", "kustomize": "Kustomize",
}
_CLOUD_PRETTY = {"azure": "Azure", "aws": "AWS", "gcp": "GCP"}
_FRONTEND = {"React", "Next.js", "Angular", "Vue", "Nuxt", "Svelte", "Remix", "React Native", "Electron"}
_BACKEND = {"FastAPI", "Django", "Flask", "Express", "Fastify", "NestJS", "Spring Boot", "Quarkus", "ASP.NET Core",
            "Gin", "Echo", "Fiber", "Rails", "Laravel", "Symfony", "Actix", "Axum"}

_COMPOSE_RE = re.compile(r"^(docker-)?compose([.\-][\w.\-]*)?\.ya?ml$", re.I)
_ENV_EXAMPLE_RE = re.compile(r"^(\.?env([.\-_][\w.\-]*)?\.(example|sample|template|dist)|(example|sample)\.env|\.env\.example)$", re.I)
_CONFIG_RE = re.compile(r"^(appsettings(\.[\w\-]+)?\.json|application(-[\w]+)?\.(properties|ya?ml)|local\.settings(\.example)?\.json)$", re.I)
_SECRETISH = re.compile(r"pass|secret|token|key|pwd|credential|sas|signature", re.I)
_HOSTISH = re.compile(r"url|host|endpoint|uri|server|broker|dsn|queue|topic|bucket|database|_api|service", re.I)
_URL_RE = re.compile(r"https?://([A-Za-z0-9._\-]+)(?::\d+)?")
_SKIP_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org", "w3.org", "schemas.", "github.com",
               "npmjs", "apache.org", "mozilla.org", "microsoft.com", "json-schema.org", "xmlsoap.org",
               "creativecommons", "googleapis.com", "gstatic", "fonts.", "cdn", "readthedocs", "wikipedia", "stackoverflow",
               "python.org", "nodejs.org", "golang.org", "pypi.org", "docker.com", "docker.io", "gnu.org", "eclipse.org",
               "springframework.org", "sun.com", "oracle.com", "schema.org", "opensource.org", "ietf.org", "yaml.org",
               "xml.org", "gravatar", "unpkg", "jsdelivr", "bootstrapcdn")

# --- IaC resource regexes ---------------------------------------------------

_TF_RES = re.compile(r'^[ \t]*resource\s+"([\w-]+)"\s+"([\w-]+)"\s*\{', re.M)
_TF_MOD = re.compile(r'^[ \t]*module\s+"([\w-]+)"', re.M)
_TF_ENGINE = re.compile(r'engine\s*=\s*"([\w-]+)"')
_BICEP_RES = re.compile(r"^[ \t]*resource\s+(\w+)\s+'([^']+)'(\s+existing)?\s*=", re.M)
_BICEP_MOD = re.compile(r"^[ \t]*module\s+(\w+)\s+'([^']+)'", re.M)
_CDK_NEW = re.compile(r"new\s+(?:(\w+)\.)?(\w+)\(\s*(?:this|scope)\s*,\s*['\"]([^'\"]+)['\"]")
_CDK_PY = re.compile(r"(\w+)\.(\w+)\(\s*self\s*,\s*['\"]([^'\"]+)['\"]")
_CDK_MAP = {
    ("lambda", "Function"): "AWS::Lambda::Function", ("lambda", "DockerImageFunction"): "AWS::Lambda::Function",
    ("s3", "Bucket"): "AWS::S3::Bucket", ("dynamodb", "Table"): "AWS::DynamoDB::Table",
    ("sqs", "Queue"): "AWS::SQS::Queue", ("sns", "Topic"): "AWS::SNS::Topic",
    ("apigateway", "RestApi"): "AWS::ApiGateway::RestApi", ("apigateway", "LambdaRestApi"): "AWS::ApiGateway::RestApi",
    ("rds", "DatabaseInstance"): "AWS::RDS::DBInstance", ("rds", "DatabaseCluster"): "AWS::RDS::DBInstance",
    ("elasticache", "CfnCacheCluster"): "AWS::ElastiCache::CacheCluster",
    ("cloudfront", "Distribution"): "AWS::CloudFront::Distribution",
}


def _add(lst: list[str], item: str) -> None:
    if item and item not in lst:
        lst.append(item)


# --------------------------------------------------------------------------- manifests


def _py_req(s: str) -> str | None:
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", s)
    return m.group(1).lower().replace("_", "-") if m else None


def _parse_manifest(path: Path, rel: str) -> list[str]:
    name = path.name.lower()
    text = read_text(path)
    deps: list[str] = []
    try:
        if name == "package.json":
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                v = data.get(key)
                if isinstance(v, dict):
                    deps += [str(k).lower() for k in v]
        elif name == "pyproject.toml":
            data = tomllib.loads(text)
            proj = data.get("project", {})
            for s in as_list(proj.get("dependencies")):
                if (n := _py_req(str(s))):
                    deps.append(n)
            for group in (proj.get("optional-dependencies") or {}).values():
                deps += [n for s in as_list(group) if (n := _py_req(str(s)))]
            for group in (data.get("dependency-groups") or {}).values():
                deps += [n for s in as_list(group) if isinstance(s, str) and (n := _py_req(s))]
            poetry = data.get("tool", {}).get("poetry", {})
            deps += [k.lower().replace("_", "-") for k in (poetry.get("dependencies") or {}) if k.lower() != "python"]
            for g in (poetry.get("group") or {}).values():
                deps += [k.lower().replace("_", "-") for k in (g.get("dependencies") or {})]
        elif name == "pipfile":
            data = tomllib.loads(text)
            for sec in ("packages", "dev-packages"):
                deps += [k.lower().replace("_", "-") for k in (data.get(sec) or {})]
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-", "git+", "http")):
                    if n := _py_req(line):
                        deps.append(n)
        elif name.endswith((".csproj", ".fsproj")):
            deps += [m.lower() for m in re.findall(r'PackageReference\s+Include="([^"]+)"', text, re.I)]
            if m := re.search(r'<Project\s+Sdk="([^"]+)"', text):
                deps.append("sdk:" + m.group(1).lower())
        elif name == "go.mod":
            deps += [m.lower() for m in re.findall(
                r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[^\s]+)\s+v[\w.\-+]+", text, re.M)]
        elif name == "pom.xml":
            for g, a in re.findall(r"<groupId>\s*([^<]+?)\s*</groupId>\s*<artifactId>\s*([^<]+?)\s*</artifactId>", text):
                deps += [f"{g}:{a}".lower(), a.lower(), g.lower()]
            if "spring-boot" in text:
                deps.append("spring-boot")
        elif name.startswith("build.gradle"):
            for g, a in re.findall(r"""["']([\w.\-]+):([\w.\-]+)(?::[^"']*)?["']""", text):
                deps += [f"{g}:{a}".lower(), a.lower()]
            if "org.springframework.boot" in text:
                deps.append("spring-boot")
            if "io.quarkus" in text:
                deps.append("io.quarkus")
        elif name == "cargo.toml":
            data = tomllib.loads(text)
            for sec in ("dependencies", "dev-dependencies"):
                deps += [k.lower() for k in (data.get(sec) or {})]
        elif name == "gemfile":
            deps += [m.lower() for m in re.findall(r"""^\s*gem\s+['"]([^'"]+)""", text, re.M)]
        elif name == "composer.json":
            data = json.loads(text)
            for key in ("require", "require-dev"):
                v = data.get(key)
                if isinstance(v, dict):
                    deps += [str(k).lower() for k in v]
    except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
        pass
    seen: set[str] = set()
    return [d for d in deps if not (d in seen or seen.add(d))]


def _has(deps: set[str], names: tuple[str, ...]) -> bool:
    for d in deps:
        for n in names:
            if d == n or d.startswith((n + "/", n + ".", n + ":")):
                return True
    return False


# --------------------------------------------------------------------------- IaC parsers


def _res(iac: str, provider: str, rtype: str, name: str, file: str, hint: str = "") -> dict:
    return {"iac": iac, "provider": provider, "type": rtype, "name": name, "file": file, "hint": hint}


def _parse_terraform(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    matches = list(_TF_RES.finditer(text))
    for i, m in enumerate(matches):
        rtype, name = m.group(1), m.group(2)
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)][:4000]
        prefix = rtype.split("_", 1)[0]
        provider = {"azurerm": "azure", "azuread": "azure", "azapi": "azure", "aws": "aws", "google": "gcp"}.get(prefix, prefix)
        hint = ""
        if rtype in ("aws_db_instance", "aws_rds_cluster", "google_sql_database_instance"):
            if e := _TF_ENGINE.search(body):
                hint = e.group(1).lower()
            elif "database_version" in body:
                hint = (re.search(r'database_version\s*=\s*"([\w]+)', body) or [None, ""])[1].lower()
        out.append(_res("terraform", provider, rtype, name, rel, hint))
        if provider in _CLOUD_PRETTY:
            _add(clouds, provider)
    for m in _TF_MOD.finditer(text):
        out.append(_res("terraform", "", "module", m.group(1), rel))


def _parse_bicep(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    matches = list(_BICEP_RES.finditer(text))
    for i, m in enumerate(matches):
        if m.group(3):  # existing
            continue
        rtype = m.group(2).split("@", 1)[0]
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)][:3000].lower()
        hint = "functionapp" if "functionapp" in body else ""
        out.append(_res("bicep", "azure", rtype, m.group(1), rel, hint))
        _add(clouds, "azure")
    for m in _BICEP_MOD.finditer(text):
        out.append(_res("bicep", "azure", "module", m.group(1), rel, m.group(2)))
    _add(clouds, "azure")


def _parse_cfn(doc: dict, rel: str, out: list[dict], clouds: list[str], iac: str) -> None:
    resources = doc.get("Resources") if isinstance(doc, dict) else None
    if not isinstance(resources, dict):
        return
    for lid, body in resources.items():
        if isinstance(body, dict) and isinstance(body.get("Type"), str):
            out.append(_res(iac, "aws", body["Type"], str(lid), rel))
    _add(clouds, "aws")


def _parse_arm(doc: dict, rel: str, out: list[dict], clouds: list[str]) -> None:
    def visit(items: Any, parent: str = "") -> None:
        for r in as_list(items):
            if not isinstance(r, dict) or not isinstance(r.get("type"), str):
                continue
            rtype = r["type"] if "/" in r["type"] and r["type"].lower().startswith("microsoft.") else f"{parent}/{r['type']}"
            hint = "functionapp" if "functionapp" in str(r.get("kind", "")).lower() else ""
            out.append(_res("arm", "azure", rtype, str(r.get("name", "")), rel, hint))
            visit(r.get("resources"), rtype)

    visit(doc.get("resources"))
    _add(clouds, "azure")


def _parse_serverless(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    prov = doc.get("provider")
    pname = (prov.get("name") if isinstance(prov, dict) else prov) or "aws"
    provider = {"aws": "aws", "azure": "azure", "google": "gcp"}.get(str(pname).lower(), "aws")
    _add(clouds, provider)
    funcs = doc.get("functions")
    if isinstance(funcs, dict):
        for fname, body in funcs.items():
            events = []
            if isinstance(body, dict):
                events = [next(iter(e)) for e in as_list(body.get("events")) if isinstance(e, dict) and e]
            out.append(_res("serverless", provider, "serverless::function", str(fname), rel, ",".join(events)))
    res = doc.get("resources")
    if isinstance(res, dict):
        _parse_cfn(res, rel, out, clouds, "serverless")


def _parse_k8s_doc(doc: Any, rel: str) -> dict | None:
    if not isinstance(doc, dict) or not isinstance(doc.get("kind"), str) or "apiVersion" not in doc:
        return None
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    kind = doc["kind"]
    obj: dict[str, Any] = {
        "kind": kind, "name": str(meta.get("name") or ""), "namespace": str(meta.get("namespace") or ""),
        "file": rel, "labels": {}, "selector": {}, "images": [], "backends": [], "ports": [],
    }
    tmpl = spec.get("template")
    if kind == "CronJob":
        jt = spec.get("jobTemplate") or {}
        tmpl = ((jt.get("spec") or {}).get("template")) if isinstance(jt, dict) else None
    if isinstance(tmpl, dict):
        tm = tmpl.get("metadata") or {}
        if isinstance(tm, dict) and isinstance(tm.get("labels"), dict):
            obj["labels"] = {str(k): str(v) for k, v in tm["labels"].items()}
        ts = tmpl.get("spec") or {}
        if isinstance(ts, dict):
            for c in as_list(ts.get("containers")):
                if isinstance(c, dict):
                    if c.get("image"):
                        obj["images"].append(str(c["image"]))
                    for p in as_list(c.get("ports")):
                        if isinstance(p, dict) and p.get("containerPort"):
                            obj["ports"].append(str(p["containerPort"]))
    if kind == "Service":
        if isinstance(spec.get("selector"), dict):
            obj["selector"] = {str(k): str(v) for k, v in spec["selector"].items()}
        for p in as_list(spec.get("ports")):
            if isinstance(p, dict) and p.get("port"):
                obj["ports"].append(str(p["port"]))
        obj["service_type"] = str(spec.get("type") or "ClusterIP")
    if kind == "Ingress":
        def find(node: Any) -> None:
            if isinstance(node, dict):
                svc = node.get("service")
                if isinstance(svc, dict) and svc.get("name"):
                    obj["backends"].append(str(svc["name"]))
                if node.get("serviceName"):
                    obj["backends"].append(str(node["serviceName"]))
                for v in node.values():
                    find(v)
            elif isinstance(node, list):
                for v in node:
                    find(v)
        find(spec)
    return obj


# --------------------------------------------------------------------------- compose


def _env_hints(env: Any) -> list[str]:
    items: list[tuple[str, str]] = []
    if isinstance(env, dict):
        items = [(str(k), "" if v is None else str(v)) for k, v in env.items()]
    else:
        for e in as_list(env):
            if isinstance(e, str):
                k, _, v = e.partition("=")
                items.append((k.strip(), v.strip()))
    hints: list[str] = []
    for k, v in items:
        if _HOSTISH.search(k):
            hints.append(f"{k}={_sanitize_value(v)}" if v and not _SECRETISH.search(k) else k)
    return hints[:8]


def _sanitize_value(v: str) -> str:
    v = re.sub(r"(://[^/:@\s]+):[^@\s]+@", r"\1:***@", v)
    return v if len(v) <= 80 else v[:77] + "..."


def _parse_compose(text: str) -> dict[str, dict]:
    doc = parse_yaml(text)
    services = doc.get("services") if isinstance(doc, dict) else None
    out: dict[str, dict] = {}
    if not isinstance(services, dict):
        return out
    for name, body in services.items():
        if not isinstance(body, dict):
            body = {}
        build = body.get("build")
        if isinstance(build, dict):
            build = build.get("context") or "."
        out[str(name)] = {
            "image": str(body.get("image") or ""),
            "build": str(build) if build else "",
            "depends_on": as_str_list(body.get("depends_on")),
            "ports": [str(p) for p in as_list(body.get("ports")) if not isinstance(p, (dict, list))]
            + [f"{p.get('published', '')}:{p.get('target', '')}" for p in as_list(body.get("ports")) if isinstance(p, dict)],
            "environment_hints": _env_hints(body.get("environment")),
        }
    return out


def image_family(image: str) -> tuple[str, str] | None:
    """(family label, kind) for a container image name, or None."""
    base = image.split("@", 1)[0].rsplit(":", 1)[0] if image else ""
    low = base.lower()
    for rx, fam, kind in _IMAGE_FAMILIES:
        if re.search(rx, low.rsplit("/", 1)[-1] if "/" in low and "supabase" not in low else low):
            return (fam, kind)
    return None


# --------------------------------------------------------------------------- CI parsers


def _short_step(step: Any) -> str:
    if not isinstance(step, dict):
        return ""
    if step.get("name"):
        return str(step["name"])
    if step.get("uses"):
        return str(step["uses"]).split("@")[0]
    run = step.get("run")
    return str(run).strip().splitlines()[0][:50] if run else ""


_DEPLOY_RE = re.compile(r"deploy|release|publish|rollout|promote|ship", re.I)


def _parse_github_workflow(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    pname = str(doc.get("name") or Path(rel).stem)
    on = doc.get("on", doc.get("true"))
    trig = ", ".join(as_str_list(on)) if on is not None else ""
    info.ci_triggers[rel] = trig[:60]
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = [s for s in (_short_step(x) for x in as_list(job.get("steps"))) if s]
        label = str(job.get("name") or jid)
        env = " ".join(steps) + " " + label + " " + str(jid)
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": pname, "id": str(jid), "label": label,
            "needs": as_str_list(job.get("needs")), "runs_on": str(job.get("runs-on") or ""),
            "steps": steps[:8], "deploy": bool(_DEPLOY_RE.search(env)) or bool(job.get("environment")),
        })
    low = text.lower()
    if "azure/" in low or "azure_" in low:
        _add(info.cloud, "azure")
    if "aws-actions/" in low:
        _add(info.cloud, "aws")
    if "google-github-actions/" in low:
        _add(info.cloud, "gcp")


def _parse_azure_pipeline(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    info.ci_triggers[rel] = ", ".join(as_str_list(doc.get("trigger")))[:60] if doc.get("trigger") else ""
    pname = Path(rel).stem
    stages = [s for s in as_list(doc.get("stages")) if isinstance(s, dict)]
    if stages:
        prev = ""
        for s in stages:
            sid = str(s.get("stage") or s.get("displayName") or "stage")
            needs = as_str_list(s["dependsOn"]) if "dependsOn" in s else ([prev] if prev else [])
            jobs_txt = json.dumps(s.get("jobs"), default=str)
            info.ci_jobs.append({
                "pipeline": rel, "pipeline_name": pname, "id": sid, "label": str(s.get("displayName") or sid),
                "needs": [n for n in needs if n], "runs_on": "", "steps": [],
                "deploy": bool(_DEPLOY_RE.search(sid)) or "deployment" in jobs_txt[:200],
            })
            prev = sid
        return
    jobs = [j for j in as_list(doc.get("jobs")) if isinstance(j, dict)]
    if jobs:
        for j in jobs:
            jid = str(j.get("job") or j.get("deployment") or j.get("displayName") or "job")
            info.ci_jobs.append({
                "pipeline": rel, "pipeline_name": pname, "id": jid, "label": str(j.get("displayName") or jid),
                "needs": as_str_list(j.get("dependsOn")), "runs_on": "",
                "steps": [s for s in (_short_step({"name": x.get("displayName"), "uses": x.get("task"), "run": x.get("script")}) for x in as_list(j.get("steps")) if isinstance(x, dict)) if s][:8],
                "deploy": "deployment" in j or bool(_DEPLOY_RE.search(jid)),
            })
    elif doc.get("steps"):
        info.ci_jobs.append({"pipeline": rel, "pipeline_name": pname, "id": "build", "label": "Build", "needs": [],
                             "runs_on": "", "steps": [], "deploy": False})


_GITLAB_RESERVED = {"stages", "variables", "include", "default", "workflow", "image", "services", "cache",
                    "before_script", "after_script", "pages"}


def _parse_gitlab(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    stages = as_str_list(doc.get("stages")) or ["build", "test", "deploy"]
    jobs = {k: v for k, v in doc.items() if isinstance(v, dict) and k not in _GITLAB_RESERVED and not k.startswith(".")
            and ("script" in v or "stage" in v or "trigger" in v)}
    by_stage: dict[str, list[str]] = {}
    for k, v in jobs.items():
        by_stage.setdefault(str(v.get("stage") or "test"), []).append(k)
    pname = ".gitlab-ci"
    for k, v in jobs.items():
        st = str(v.get("stage") or "test")
        if "needs" in v:
            needs = [str(n.get("job")) if isinstance(n, dict) else str(n) for n in as_list(v["needs"]) if n]
        else:
            idx = stages.index(st) if st in stages else 0
            needs = by_stage.get(stages[idx - 1], []) if idx > 0 else []
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": pname, "id": k, "label": k, "needs": needs[:6], "runs_on": "",
            "steps": [], "stage": st, "deploy": bool(_DEPLOY_RE.search(k + st)),
        })


def _parse_named_steps(text: str, rel: str, info: RepoInfo, rx: str) -> None:
    prev = ""
    for name in re.findall(rx, text, re.M):
        name = name.strip().strip("'\"")
        if not name or any(j["id"] == name and j["pipeline"] == rel for j in info.ci_jobs):
            continue
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": Path(rel).name, "id": name, "label": name,
            "needs": [prev] if prev else [], "runs_on": "", "steps": [], "deploy": bool(_DEPLOY_RE.search(name)),
        })
        prev = name


# --------------------------------------------------------------------------- scan


def _is_test_path(rel: str) -> bool:
    parts = rel.lower().split("/")
    if any(p in _TEST_PARTS for p in parts[:-1]):
        return True
    n = parts[-1]
    return ".test." in n or ".spec." in n or n.startswith("test_") or n.endswith(("_test.go", "_test.py", "tests.cs"))


def scan(path: str | Path) -> RepoInfo:
    """Profile one repository folder. Fast: one directory walk plus a few hundred small reads."""
    root = resolve_dir(path)
    gi = GitIgnore(root)
    files = walk(root, gi)
    info = RepoInfo(path=root, name=root.name or str(root))
    info.is_git = (root / ".git").exists()
    info.file_count = len(files)

    langs: Counter[str] = Counter()
    code_bytes = 0
    manifests: list[FileEntry] = []
    dockerfiles: list[str] = []
    composes: list[str] = []
    workflows: list[str] = []
    ci_other: list[str] = []
    tf_files: list[str] = []
    bicep_files: list[str] = []
    yaml_cands: list[FileEntry] = []
    json_cands: list[FileEntry] = []
    env_examples: list[str] = []
    configs: list[str] = []
    samples: list[FileEntry] = []
    entry_cands: list[FileEntry] = []
    readme_rel = ""
    markers: set[str] = set()
    helm_dirs: list[str] = []
    cdk_dirs: list[str] = []
    all_rel = set()

    for f in files:
        name, rel = f.name, f.rel
        low = name.lower()
        ext = os.path.splitext(low)[1]
        depth = f.depth
        all_rel.add(rel.lower())
        lang = _LANG.get(ext)
        if lang:
            langs[lang] += 1
            if lang not in ("HTML", "CSS", "SQL"):
                code_bytes += f.size
            if ext in _SAMPLE_EXT and f.size < 60_000 and not _is_test_path(rel):
                samples.append(f)
        if low in _MANIFEST_NAMES or ext in _MANIFEST_EXT or (low.startswith("requirements") and ext == ".txt"):
            manifests.append(f)
        if low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile"):
            dockerfiles.append(rel)
        if _COMPOSE_RE.match(name):
            composes.append(rel)
            continue
        if rel.startswith(".github/workflows/") and ext in (".yml", ".yaml"):
            workflows.append(rel)
            continue
        if depth <= 1 and low in ("azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml", "jenkinsfile",
                                  "bitbucket-pipelines.yml", ".travis.yml", "cloudbuild.yaml", "cloudbuild.yml",
                                  "buildspec.yml", ".drone.yml") or rel == ".circleci/config.yml":
            ci_other.append(rel)
            continue
        if ext == ".tf" and f.size < 400_000:
            tf_files.append(rel)
        elif ext == ".bicep" and f.size < 400_000:
            bicep_files.append(rel)
        elif low in ("cdk.json",):
            cdk_dirs.append(rel.rsplit("/", 1)[0] if "/" in rel else "")
            markers.add("cdk")
        elif low in ("pulumi.yaml", "pulumi.yml"):
            markers.add("pulumi")
        elif low == "chart.yaml":
            helm_dirs.append(rel.rsplit("/", 1)[0] if "/" in rel else "")
            markers.add("helm")
        elif low in ("kustomization.yaml", "kustomization.yml"):
            markers.add("kustomize")
        elif low == "host.json":
            markers.add("azure-functions")
        elif low == "azure.yaml" or low == "azure.yml":
            markers.add("azd")
        elif low in ("serverless.yml", "serverless.yaml"):
            yaml_cands.append(f)
            markers.add("serverless")
        elif low in ("next.config.js", "next.config.mjs", "next.config.ts"):
            markers.add("next")
        elif low == "angular.json":
            markers.add("angular")
        elif low.startswith("nuxt.config."):
            markers.add("nuxt")
        elif low == "svelte.config.js":
            markers.add("svelte")
        elif low == "manage.py":
            markers.add("django")
        elif low in ("app.yaml", "app.yml") and depth == 0:
            markers.add("gae")
        elif low == "firebase.json":
            markers.add("firebase")
        elif low == "samconfig.toml":
            markers.add("sam")
        elif _ENV_EXAMPLE_RE.match(name):
            env_examples.append(rel)
        elif _CONFIG_RE.match(name) and f.size < 100_000:
            configs.append(rel)
        elif ext in (".yaml", ".yml") and f.size < 200_000:
            yaml_cands.append(f)
        elif ext == ".json" and f.size < 400_000 and re.search(
                r"template|azuredeploy|deploy|\.arm\.|infra|stack", low) and low not in ("package.json", "package-lock.json"):
            json_cands.append(f)
        if low.startswith("readme") and depth == 0 and (not readme_rel or ext in (".md", "")):
            readme_rel = rel
        if low in _ENTRY_NAMES and depth <= 3:
            entry_cands.append(f)
        elif low.endswith("application.java") and depth <= 8 and "src/main/" in rel:
            entry_cands.append(f)

    # languages / loc
    info.languages = dict(sorted(langs.items(), key=lambda kv: (-kv[1], kv[0])))
    info.loc_estimate = code_bytes // 36

    # ---- manifests & dependencies
    manifests.sort(key=lambda f: (f.depth, f.rel))
    info.manifests = [m.rel for m in manifests[:60]]
    deps: set[str] = set()
    for m in manifests[:30]:
        d = _parse_manifest(root / m.rel, m.rel)
        if d:
            info.dependencies[m.rel] = d[:80]
            deps.update(d)

    # ---- containers & compose
    info.containers = sorted(dockerfiles, key=lambda r: (r.count("/"), r))[:30]
    compose_text = ""
    for rel in sorted(composes, key=lambda r: (r.count("/"), r))[:10]:
        text = read_text(root / rel, 200_000)
        compose_text += "\n" + text
        info.compose_services.update(_parse_compose(text))
        _add(info.iac, rel)
        _add(info.iac_kinds, "docker-compose")

    # ---- IaC: terraform / bicep
    clouds: list[str] = []
    for rel in sorted(tf_files, key=lambda r: (r.count("/"), r))[:80]:
        _parse_terraform(read_text(root / rel, 400_000), rel, info.resources, clouds)
        _add(info.iac, rel)
        _add(info.iac_kinds, "terraform")
    for rel in sorted(bicep_files, key=lambda r: (r.count("/"), r))[:80]:
        _parse_bicep(read_text(root / rel, 400_000), rel, info.resources, clouds)
        _add(info.iac, rel)
        _add(info.iac_kinds, "bicep")

    # ---- IaC / k8s from yaml & json candidates
    def hinted(f: FileEntry) -> tuple[int, int, str]:
        low = f.rel.lower()
        hint = any(h in low for h in ("k8s", "kube", "manifest", "deploy", "helm", "chart", "infra", "cloudformation",
                                      "template", "stack", "sam", "serverless"))
        return (0 if hint else 1, f.depth, f.rel)

    k8s_files = 0
    helm_prefixes = tuple(h + "/" if h else "" for h in helm_dirs)
    for f in sorted(yaml_cands, key=hinted)[:200]:
        text = read_text(root / f.rel, 200_000)
        low = f.name.lower()
        if low.startswith("serverless."):
            _parse_serverless(text, f.rel, info.resources, clouds)
            _add(info.iac, f.rel)
            _add(info.iac_kinds, "serverless")
            continue
        if "AWSTemplateFormatVersion" in text or re.search(r"^\s+Type:\s*['\"]?AWS::", text, re.M):
            sam = "Serverless-2016-10-31" in text or "AWS::Serverless" in text
            _parse_cfn(parse_yaml(text), f.rel, info.resources, clouds, "sam" if sam else "cloudformation")
            _add(info.iac, f.rel)
            _add(info.iac_kinds, "sam" if sam else "cloudformation")
            continue
        if re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:\s*\w+", text, re.M):
            in_helm = "/templates/" in "/" + f.rel and any(f.rel.startswith(p) for p in helm_prefixes)
            if in_helm:
                for k in re.findall(r"^kind:\s*(\w+)", text, re.M):
                    info.k8s_objects.append({"kind": k, "name": Path(f.rel).stem, "namespace": "", "file": f.rel,
                                             "labels": {}, "selector": {}, "images": [], "backends": [], "ports": [],
                                             "helm": True})
                _add(info.iac, f.rel)
                continue
            found = False
            for doc in yaml_docs(text):
                obj = _parse_k8s_doc(doc, f.rel)
                if obj:
                    info.k8s_objects.append(obj)
                    found = True
            if found:
                k8s_files += 1
                _add(info.iac, f.rel)
                _add(info.iac_kinds, "kubernetes")
    for f in sorted(json_cands, key=hinted)[:60]:
        text = read_text(root / f.rel, 400_000)
        if "deploymentTemplate" in text or "schema.management.azure.com" in text:
            try:
                _parse_arm(json.loads(text), f.rel, info.resources, clouds)
            except ValueError:
                continue
            _add(info.iac, f.rel)
            _add(info.iac_kinds, "arm")
        elif "AWSTemplateFormatVersion" in text or '"AWS::' in text:
            try:
                doc = json.loads(text)
            except ValueError:
                continue
            _parse_cfn(doc, f.rel, info.resources, clouds, "cloudformation")
            _add(info.iac, f.rel)
            _add(info.iac_kinds, "cloudformation")
    for h in helm_dirs:
        _add(info.iac, (h + "/Chart.yaml") if h else "Chart.yaml")
    for mk in ("helm", "pulumi", "kustomize"):
        if mk in markers:
            _add(info.iac_kinds, mk)
    if "pulumi" in markers:
        for rel in sorted(all_rel):
            if rel.endswith("pulumi.yaml") or rel.endswith("pulumi.yml"):
                _add(info.iac, rel)
    if "cdk" in markers:
        _add(info.iac_kinds, "cdk")
        for d in cdk_dirs:
            _add(info.iac, (d + "/cdk.json") if d else "cdk.json")
        _scan_cdk(root, files, cdk_dirs, info)
        _add(clouds, "aws")
    if "serverless" in markers and "serverless" not in info.iac_kinds:
        _add(info.iac_kinds, "serverless")

    # ---- CI
    for rel in sorted(workflows)[:20]:
        _parse_github_workflow(read_text(root / rel, 200_000), rel, info)
        _add(info.ci, rel)
    for rel in ci_other:
        text = read_text(root / rel, 200_000)
        _add(info.ci, rel)
        low = rel.lower()
        if "azure-pipelines" in low:
            _parse_azure_pipeline(text, rel, info)
        elif low.endswith(".gitlab-ci.yml"):
            _parse_gitlab(text, rel, info)
        elif low.endswith("jenkinsfile"):
            _parse_named_steps(text, rel, info, r"stage\s*\(\s*['\"]([^'\"]+)['\"]")
        elif low.endswith("bitbucket-pipelines.yml"):
            _parse_named_steps(text, rel, info, r"^\s*(?:-\s*)?name:\s*(.+?)\s*$")

    # ---- text blobs for keyword detection
    env_lines: list[str] = []
    blob_parts: list[str] = [compose_text]
    for rel in env_examples[:6] + configs[:10]:
        text = read_text(root / rel, 40_000)
        blob_parts.append(text)
        if rel in env_examples[:6]:
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_lines.append(k.strip() + "=" + v.strip().strip("\"'"))
    sample_sorted = sorted(samples, key=lambda f: (f.depth, f.rel))[:150]
    for f in sample_sorted:
        blob_parts.append(read_text(root / f.rel, 16_000))
    blob = "\n".join(blob_parts)
    blob_low = blob.lower()
    env_keys = "\n".join(l.split("=", 1)[0].upper() for l in env_lines)
    env_keys += "\n" + "\n".join(re.findall(r"^\s*-?\s*([A-Z][A-Z0-9_]{3,})\s*[:=]", compose_text, re.M))

    # ---- frameworks
    for fw, names in _FRAMEWORKS:
        if _has(deps, names):
            _add(info.frameworks, fw)
    if "next" in markers:
        _add(info.frameworks, "Next.js")
    if "angular" in markers:
        _add(info.frameworks, "Angular")
    if "nuxt" in markers:
        _add(info.frameworks, "Nuxt")
    if "svelte" in markers:
        _add(info.frameworks, "Svelte")
    if "django" in markers and "Django" not in info.frameworks:
        info.frameworks.append("Django")
    if "azure-functions" in markers and not any("Azure Functions" in f for f in info.frameworks):
        info.frameworks.append(".NET Azure Functions" if "C#" in info.languages else "Azure Functions")
    if "serverless" in markers or "sam" in markers or any(r["type"].startswith("AWS::Serverless") for r in info.resources):
        if any(r["provider"] == "aws" for r in info.resources if r["iac"] in ("serverless", "sam")):
            _add(info.frameworks, "AWS Lambda")
    # Next.js ships React; keep both but put the meta-framework first.
    if "Next.js" in info.frameworks and "React" in info.frameworks:
        info.frameworks.remove("React")
        info.frameworks.insert(info.frameworks.index("Next.js") + 1, "React")

    # ---- databases / messaging / storage / external
    for label, names, rx in _DATABASES:
        if _has(deps, names) or (rx and re.search(rx, blob_low)):
            _add(info.databases, label)
    for label, names, rx in _MESSAGING:
        if _has(deps, names) or (rx and re.search(rx, blob_low)):
            _add(info.messaging, label)
    for label, names, rx in _STORAGE:
        if _has(deps, names) or (rx and re.search(rx, blob_low)):
            _add(info.storage, label)
    for label, names, prefixes in _EXTERNAL:
        if _has(deps, names) or any(p in env_keys for p in prefixes):
            _add(info.external_apis, label)
    # compose images contribute infra families
    for svc in info.compose_services.values():
        fam = image_family(svc.get("image", ""))
        if fam and fam[0]:
            target = getattr(info, _FAMILY_LISTS.get(fam[1], "databases"))
            _add(target, fam[0])
    # IaC resources contribute too
    from .heuristic_tables import resource_family  # local import: avoid cycle at module load

    for r in info.resources:
        fam = resource_family(r)
        if fam:
            kind, label = fam
            _add(getattr(info, _FAMILY_LISTS.get(kind, "databases")), label)

    # ---- cloud
    for cloud, prefixes in _CLOUD_PREFIXES.items():
        if any(d.startswith(prefixes) for d in deps):
            _add(info.cloud, cloud)
    for c in clouds:
        _add(info.cloud, c)
    if {"azd", "azure-functions"} & markers:
        _add(info.cloud, "azure")
    if {"gae", "firebase"} & markers:
        _add(info.cloud, "gcp")
    if "sam" in markers:
        _add(info.cloud, "aws")
    if any(c in ci for ci in info.ci for c in ("cloudbuild",)):
        _add(info.cloud, "gcp")
    if any(ci.endswith("buildspec.yml") for ci in info.ci):
        _add(info.cloud, "aws")
    info.cloud.sort(key=lambda c: ["azure", "aws", "gcp"].index(c))

    # ---- entry points
    entries: list[str] = []
    for f in sorted(entry_cands, key=lambda f: (f.depth, f.rel)):
        _add(entries, f.rel)
    for f in files:
        if f.name == "main.go" and f.rel.startswith("cmd/"):
            _add(entries, f.rel)
        if len(entries) >= 15:
            break
    info.entrypoints = sorted(entries, key=lambda r: (r.count("/"), r))[:15]

    # ---- references (other systems named in config)
    refs: list[str] = []
    for line in env_lines:
        k, _, v = line.partition("=")
        if _HOSTISH.search(k) and v and not _SECRETISH.search(k):
            refs.append(f"{k}={_sanitize_value(v)}")
    for svc_name, svc in info.compose_services.items():
        refs.extend(f"{svc_name}:{h}" for h in svc.get("environment_hints", []))
    hosts: list[str] = []
    for host in _URL_RE.findall(blob):
        h = host.lower().rstrip(".")
        if h and not any(x in h for x in _SKIP_HOSTS) and h not in hosts:
            hosts.append(h)
    refs.extend(f"url:{h}" for h in hosts[:30])
    info.references = refs[:80]

    # ---- readme
    if readme_rel:
        text = read_text(root / readme_rel, 20_000)
        info.readme = "\n".join(text.splitlines()[:80])[:6000]

    _finish(info, all_rel)
    return info


def _scan_cdk(root: Path, files: list[FileEntry], cdk_dirs: list[str], info: RepoInfo) -> None:
    n = 0
    for f in files:
        if not f.rel.endswith((".ts", ".py")) or f.size > 100_000 or _is_test_path(f.rel):
            continue
        if not any(f.rel.startswith(d + "/") or not d for d in cdk_dirs):
            continue
        text = read_text(root / f.rel, 100_000)
        rx = _CDK_NEW if f.rel.endswith(".ts") else _CDK_PY
        for ns, cls, ident in rx.findall(text):
            t = _CDK_MAP.get((ns.lower().replace("_", ""), cls)) or _CDK_MAP.get((ns.split("_")[0], cls))
            if t:
                info.resources.append(_res("cdk", "aws", t, ident, f.rel))
                n += 1
        if n > 60:
            break


def _finish(info: RepoInfo, all_rel: set[str]) -> None:
    info.suggested_types = _suggest_types(info, all_rel)
    info.summary = _summarize(info)


def _suggest_types(info: RepoInfo, all_rel: set[str]) -> list[str]:
    out = ["architecture"]
    has_cloud_res = any(r["provider"] in _CLOUD_PRETTY for r in info.resources)
    if has_cloud_res or info.cloud:
        out.append("cloud")
    out.append("c4-container")
    if info.compose_services or info.k8s_objects or info.containers or has_cloud_res:
        out.append("deployment")
    if info.ci_jobs or info.ci:
        out.append("pipeline")
    erd_signal = any(
        r.endswith(("models.py", "schema.prisma", ".sql", "entities.py")) or "/migrations/" in "/" + r or "/entities/" in r
        or "/models/" in r for r in all_rel
    )
    if info.databases and erd_signal:
        out.append("erd")
    if info.messaging:
        out.append("dataflow")
    return out


def _summarize(info: RepoInfo) -> str:
    primary = next((l for l in info.languages if l not in _NON_PRIMARY), "")
    fe = [f for f in info.frameworks if f in _FRONTEND]
    be = [f for f in info.frameworks if f not in _FRONTEND]
    iac_main = [k for k in info.iac_kinds if k not in ("docker-compose", "kubernetes", "helm", "kustomize")]
    n_res = sum(1 for r in info.resources if r["type"] != "module")
    app_frameworks = info.frameworks
    if not app_frameworks and iac_main and (not primary or info.languages.get(primary, 0) < 3 or primary in ("Shell",)):
        cloud = " and ".join(_CLOUD_PRETTY[c] for c in info.cloud) if info.cloud else "cloud"
        base = f"{' + '.join(_IAC_PRETTY.get(k, k) for k in iac_main)} infrastructure for {cloud}"
        if n_res:
            base += f" ({n_res} resources)"
        return base
    fw = " + ".join((be[:1] + fe[:1]) if (be and fe) else (info.frameworks[:2]))
    kind = "web app" if fe and not be else ("service" if be else "project")
    parts = [" ".join(p for p in (primary, fw, kind) if p)]
    data = (info.databases + [m for m in info.messaging if m != "Celery" or True])[:4]
    summary = parts[0]
    if data:
        summary += " with " + (", ".join(data[:-1]) + " and " + data[-1] if len(data) > 1 else data[0])
    if info.cloud and iac_main:
        summary += f", deployed to {' and '.join(_CLOUD_PRETTY[c] for c in info.cloud)} via {', '.join(_IAC_PRETTY.get(k, k) for k in iac_main)}"
    elif "kubernetes" in info.iac_kinds or "helm" in info.iac_kinds:
        summary += ", deployed to Kubernetes"
    elif info.cloud:
        summary += f", using {' and '.join(_CLOUD_PRETTY[c] for c in info.cloud)} services"
    elif info.compose_services:
        summary += ", run with Docker Compose"
    elif info.containers:
        summary += ", containerized with Docker"
    if info.ci:
        ci_names = []
        for c in info.ci:
            n = ("GitHub Actions" if c.startswith(".github/") else "Azure Pipelines" if "azure-pipelines" in c
                 else "GitLab CI" if "gitlab" in c else "Jenkins" if "Jenkinsfile" in c else "CI")
            if n not in ci_names:
                ci_names.append(n)
        summary += f"; CI on {', '.join(ci_names)}"
    return summary


# --------------------------------------------------------------------------- discovery

_ROOT_MARKERS = {
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "gemfile", "composer.json", "pipfile", "setup.py", "dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml", "main.tf", "main.bicep", "serverless.yml", "cdk.json",
    "host.json",
}


def _is_repo(p: Path) -> bool:
    if (p / ".git").exists():
        return True
    try:
        with os.scandir(p) as it:
            for e in it:
                low = e.name.lower()
                if e.is_file(follow_symlinks=False) and (
                    low in _ROOT_MARKERS or low.endswith((".csproj", ".sln", ".fsproj", ".tf", ".bicep"))
                ):
                    return True
    except OSError:
        return False
    return False


def discover(path: str | Path, max_depth: int = 3) -> list[RepoInfo]:
    """Find and profile repositories at or below path.

    A folder that is itself a repo (has .git or a manifest) yields one RepoInfo; otherwise repos are searched
    for below it (up to max_depth levels) and returned sorted by name.
    """
    root = resolve_dir(path)
    if _is_repo(root):
        return [scan(root)]
    found: list[Path] = []
    level = [root]
    for _ in range(max(1, max_depth)):
        nxt: list[Path] = []
        for d in level:
            try:
                with os.scandir(d) as it:
                    subs = sorted(
                        (e for e in it if e.is_dir(follow_symlinks=False)
                         and not is_ignored_dir(e.name) and not e.name.startswith(".")),
                        key=lambda e: e.name,
                    )
            except OSError:
                continue
            for e in subs:
                p = Path(e.path)
                if _is_repo(p):
                    found.append(p)
                else:
                    nxt.append(p)
        level = nxt
        if not level or len(found) >= 200:
            break
    if not found:
        return [scan(root)]
    repos = [scan(p) for p in found[:200]]
    repos.sort(key=lambda r: (r.name.lower(), str(r.path)))
    return repos
