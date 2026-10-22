"""References to other systems: hostname-like env vars, compose hints and external URLs."""

from __future__ import annotations

import re

from ..model import RepoInfo
from ..text import sanitize_value
from .corpus import Corpus
from .hints import HOSTISH, SECRETISH


URL_RE = re.compile(r"https?://([A-Za-z0-9._\-]+)(?::\d+)?")

# Environment variables read in source: process.env.X, os.environ["X"], os.getenv("X"), Environment.GetEnvironmentVariable("X")
ENV_READ_RE = re.compile(
    r"(?:process\.env\.|import\.meta\.env\.|os\.environ(?:\.get)?[\[(]\s*[\"']|getenv\(\s*[\"']|"
    r"GetEnvironmentVariable\(\s*\"|System\.getenv\(\s*\"|ENV\[\s*[\"'])([A-Z][A-Z0-9_]{2,})"
)

SKIP_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org", "w3.org", "schemas.", "github.com",
               "npmjs", "apache.org", "mozilla.org", "microsoft.com", "json-schema.org", "xmlsoap.org",
               "creativecommons", "googleapis.com", "gstatic", "fonts.", "cdn", "readthedocs", "wikipedia", "stackoverflow",
               "python.org", "nodejs.org", "golang.org", "pypi.org", "docker.com", "docker.io", "gnu.org", "eclipse.org",
               "springframework.org", "sun.com", "oracle.com", "schema.org", "opensource.org", "ietf.org", "yaml.org",
               "xml.org", "gravatar", "unpkg", "jsdelivr", "bootstrapcdn")


def build_references(info: RepoInfo, corpus: Corpus) -> list[str]:
    refs: list[str] = []
    for line in corpus.env_lines:
        k, _, v = line.partition("=")
        if HOSTISH.search(k) and v and not SECRETISH.search(k):
            refs.append(f"{k}={sanitize_value(v)}")
    for svc_name, svc in info.compose_services.items():
        refs.extend(f"{svc_name}:{h}" for h in svc.get("environment_hints", []))
    for var in dict.fromkeys(ENV_READ_RE.findall(corpus.blob)):
        if HOSTISH.search(var) and not SECRETISH.search(var):
            refs.append(f"env:{var}")
    hosts: list[str] = []
    for host in URL_RE.findall(corpus.blob):
        h = host.lower().rstrip(".")
        if h and not any(x in h for x in SKIP_HOSTS) and h not in hosts:
            hosts.append(h)
    refs.extend(f"url:{h}" for h in hosts[:30])
    return refs[:80]
