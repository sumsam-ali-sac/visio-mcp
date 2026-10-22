"""Naming helpers for generated diagrams: ids, readable names, role suffixes and titles."""

from __future__ import annotations

import re

from ..model import RepoInfo


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "n"


def humanize(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").replace("-", " ")
    return " ".join(s.split())


ROLE_SUFFIX = {"database": "DB", "cache": "Cache", "queue": "Queue", "storage": "Storage"}


def kind_suffix(kind: str) -> str:
    base = kind.split("-", 1)[-1] if kind.startswith(("azure-", "aws-", "gcp-")) else kind
    for words, suffix in ((("rds", "aurora", "sql", "dynamodb", "cosmos", "spanner", "firestore", "database",
                            "bigtable", "alloydb"), "DB"),
                          (("redis", "elasticache", "memorystore", "cache"), "Cache"),
                          (("s3", "blob", "storage"), "Storage"),
                          (("sqs", "sns", "service-bus", "pubsub", "queue", "topic", "event"), "Queue"),
                          (("ecs", "eks", "fargate", "aks", "gke", "container", "app-service", "cloud-run",
                            "service", "webapp", "ec2", "vm", "compute"), "Service"),
                          (("lambda", "function"), "Function"),
                          (("alb", "load", "gateway", "front-door", "cloudfront", "cdn"), "Gateway")):
        if any(w in base for w in words):
            return suffix
    return ""


def diagram_title(repos: list[RepoInfo], suffix: str) -> str:
    if len(repos) == 1:
        return f"{repos[0].name} {suffix}"
    parent = repos[0].path.parent.name if repos else ""
    same_parent = len({r.path.parent for r in repos}) == 1
    return f"{parent if same_parent and parent else f'{len(repos)} repositories'} {suffix}"
