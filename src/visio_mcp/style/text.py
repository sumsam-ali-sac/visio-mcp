"""Text helpers: label casing with a fixed-spelling word list, width estimate and word wrap."""

from __future__ import annotations

import re

_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "via", "vs", "with"}
# Words with a fixed spelling, matched case-insensitively.
_FIXED = {w.lower(): w for w in (
    "API", "APIs", "AWS", "GCP", "UI", "UX", "DB", "SQL", "NoSQL", "SDK", "CLI", "CDN", "DNS", "VPN", "VPC", "VNet",
    "HTTP", "HTTPS", "REST", "gRPC", "GraphQL", "JSON", "XML", "CSV", "JWT", "OAuth", "OIDC", "SSO", "SAML", "IAM",
    "AD", "AKS", "EKS", "GKE", "ECS", "EC2", "S3", "RDS", "SQS", "SNS", "IoT", "ML", "AI", "LLM", "ETL", "ELT", "CI",
    "CD", "CI/CD", "K8s", "VM", "VMs", "OS", "iOS", "macOS", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka",
    "RabbitMQ", "GitHub", "GitLab", "DevOps", "PowerShell", "JavaScript", "TypeScript", "Node.js", "Next.js",
    "React", "Vue", "Angular", ".NET", "ASP.NET", "FastAPI", "Django", "Flask", "WebSocket", "WebSockets",
    "OpenAI", "ID", "IDs", "URL", "URLs", "PDF", "SMTP", "SMS", "TCP", "UDP", "IP", "LAN", "WAN", "WAF", "TLS",
    "SSL", "SaaS", "PaaS", "IaaS", "B2B", "B2C", "CRM", "ERP", "BI", "KPI", "SLA", "QA", "PR", "PRs", "VS",
    "DynamoDB", "CosmosDB", "BigQuery", "Pub/Sub", "Entra", "SharePoint", "OneDrive", "Dataverse", "Power BI",
)}


def title_case(text: str) -> str:
    """Smart Title Case for node and group labels.

    Keeps acronyms and product spellings (API, PostgreSQL, iOS), mixed-case words
    (camelCase identifiers), and anything with digits as written; lowercases short
    joining words except at the start.
    """
    words = re.split(r"(\s+)", text.strip())
    out: list[str] = []
    first = True
    for w in words:
        if not w or w.isspace():
            out.append(w)
            continue
        core = w.strip("()[]{}\"',.:;")
        lead, trail = w[: w.find(core)] if core else "", w[w.find(core) + len(core):] if core else ""
        fixed = _FIXED.get(core.lower())
        if fixed:
            new = fixed
        elif any(c.isdigit() for c in core) or (core[1:] != core[1:].lower() and not core.isupper()):
            new = core  # v2, camelCase, eTag: keep
        elif core.isupper() and 2 <= len(core) <= 5:
            new = core  # an acronym we don't know
        elif not first and core.lower() in _SMALL:
            new = core.lower()
        else:
            new = "-".join(p[:1].upper() + p[1:].lower() if p else p for p in core.split("-"))
        out.append(lead + new + trail)
        first = False
    return "".join(out)


def sentence_case(text: str) -> str:
    """Edge labels read as lowercase phrases ('reads from', 'yes', 'HTTPS'): capitalized
    plain words are lowered, acronyms and product names keep their spelling."""
    out = []
    for w in re.split(r"(\s+)", text.strip()):
        core = w.strip("()[]\"',.:;")
        if not core or w.isspace() or _FIXED.get(core.lower()) or any(c.isdigit() for c in core):
            out.append(_FIXED.get(core.lower(), core).join(w.split(core, 1)) if core else w)
        elif core[:1].isupper() and core[1:].islower():
            out.append(w.replace(core, core.lower(), 1))
        else:
            out.append(w)
    return "".join(out)


def text_width(text: str, size_pt: float, bold: bool = False) -> float:
    """Approximate rendered width in inches of one line (Segoe UI / Arial metrics)."""
    narrow = sum(1 for c in text if c in "iljtf.,:;'|!I ()[]")
    wide = sum(1 for c in text if c in "MWmw@%")
    units = len(text) - narrow * 0.45 + wide * 0.35
    return units * size_pt * (0.56 if bold else 0.52) / 72.0


def wrap(text: str, size_pt: float, max_w: float, bold: bool = False) -> list[str]:
    """Greedy word wrap to max_w inches."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if cur and text_width(cand, size_pt, bold) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines or [""]
