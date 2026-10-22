"""Docker Compose: find compose files, parse services, and classify container images."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..lists import add_unique, as_list, as_str_list
from ..model import RepoInfo
from ..text import read_text, sanitize_value
from ..yaml import parse_yaml
from .hints import HOSTISH, SECRETISH


COMPOSE_RE = re.compile(r"^(docker-)?compose([.\-][\w.\-]*)?\.ya?ml$", re.I)


IMAGE_FAMILIES: list[tuple[str, str, str]] = [
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

FAMILY_LISTS = {"database": "databases", "cache": "databases", "queue": "messaging", "storage": "storage"}


def env_hints(env: Any) -> list[str]:
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
        if HOSTISH.search(k):
            hints.append(f"{k}={sanitize_value(v)}" if v and not SECRETISH.search(k) else k)
    return hints[:8]


def parse_compose(text: str) -> dict[str, dict]:
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
            "environment_hints": env_hints(body.get("environment")),
        }
    return out


def image_family(image: str) -> tuple[str, str] | None:
    """(family label, kind) for a container image name, or None."""
    base = image.split("@", 1)[0].rsplit(":", 1)[0] if image else ""
    low = base.lower()
    for rx, fam, kind in IMAGE_FAMILIES:
        if re.search(rx, low.rsplit("/", 1)[-1] if "/" in low and "supabase" not in low else low):
            return (fam, kind)
    return None


def read_compose(root: Path, rels: list[str], info: RepoInfo) -> str:
    """Parse up to 10 compose files into info.compose_services; return their concatenated text."""
    text_all = ""
    for rel in sorted(rels, key=lambda r: (r.count("/"), r))[:10]:
        text = read_text(root / rel, 200_000)
        text_all += "\n" + text
        info.compose_services.update(parse_compose(text))
        add_unique(info.iac, rel)
        add_unique(info.iac_kinds, "docker-compose")
    return text_all
