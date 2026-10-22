"""Data stores, messaging, object storage and external APIs from dependencies, config text and infra."""

from __future__ import annotations

import re

from ..lists import add_unique
from ..model import RepoInfo
from ..resources import resource_family
from .compose import FAMILY_LISTS, image_family
from .corpus import Corpus
from .manifests import has


DATABASES: list[tuple[str, tuple[str, ...], str]] = [
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

MESSAGING: list[tuple[str, tuple[str, ...], str]] = [
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

STORAGE: list[tuple[str, tuple[str, ...], str]] = [
    ("Azure Blob Storage", ("azure-storage-blob", "@azure/storage-blob", "azure.storage.blobs",
                            "microsoft.azure.storage.blob", "azure.storage.queues"), r"blob\.core\.windows\.net"),
    ("S3", ("@aws-sdk/client-s3", "awssdk.s3", "s3transfer", "aws-sdk-s3"), r"client\(\s*['\"]s3['\"]|resource\(\s*['\"]s3['\"]|\.s3\.amazonaws\.com"),
    ("Cloud Storage", ("google-cloud-storage", "@google-cloud/storage"), r"storage\.googleapis\.com"),
    ("MinIO", ("minio",), r"minio_"),
]

EXTERNAL: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
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


def detect_data(info: RepoInfo, deps: set[str], corpus: Corpus) -> None:
    blob_low = corpus.blob.lower()
    for label, names, rx in DATABASES:
        if has(deps, names) or (rx and re.search(rx, blob_low)):
            add_unique(info.databases, label)
    for label, names, rx in MESSAGING:
        if has(deps, names) or (rx and re.search(rx, blob_low)):
            add_unique(info.messaging, label)
    for label, names, rx in STORAGE:
        if has(deps, names) or (rx and re.search(rx, blob_low)):
            add_unique(info.storage, label)
    for label, names, prefixes in EXTERNAL:
        if has(deps, names) or any(p in corpus.env_keys for p in prefixes):
            add_unique(info.external_apis, label)
    for svc in info.compose_services.values():  # compose images contribute infra families
        fam = image_family(svc.get("image", ""))
        if fam and fam[0]:
            add_unique(getattr(info, FAMILY_LISTS.get(fam[1], "databases")), fam[0])
    for r in info.resources:  # so do IaC resources
        fam = resource_family(r)
        if fam:
            kind, label = fam
            add_unique(getattr(info, FAMILY_LISTS.get(kind, "databases")), label)
