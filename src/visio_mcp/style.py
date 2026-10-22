"""Themes, typography, text casing and node sizing: how a diagram looks.

A Theme maps semantic roles (node category, group kind, edge, title) to concrete
styles. Every renderer (Visio COM, the native .vsdx writer, SVG preview) reads the
same Theme, so all outputs look alike.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Literal

LinePattern = Literal["solid", "dashed", "dotted"]

# Node categories (catalog.Kind.category). Each theme styles every one of them.
CATEGORIES = (
    "terminal",  # start / end
    "flow",  # process steps
    "decision",
    "data",  # databases, storage, caches
    "compute",  # services, apps, functions, servers
    "integration",  # queues, buses, gateways, APIs
    "client",  # browsers, mobile, desktop
    "person",  # users, actors
    "external",  # third-party systems
    "network",  # routers, switches, firewalls, load balancers
    "security",  # identity, key vaults, firewalls
    "org",  # org chart positions
    "entity",  # ERD tables
    "note",
    "generic",
)


@dataclass(frozen=True)
class TextStyle:
    font: str = "Segoe UI"
    size: float = 10.0  # points
    color: str = "#1F2937"
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class ShapeStyle:
    fill: str | None = "#FFFFFF"  # None = no fill
    line: str | None = "#94A3B8"  # None = no line
    line_weight: float = 1.0  # points
    line_pattern: LinePattern = "solid"
    rounding: float = 0.0  # corner radius, inches
    shadow: bool = False
    text: TextStyle = TextStyle()


@dataclass(frozen=True)
class GroupStyle:
    shape: ShapeStyle
    header: TextStyle  # the group label, drawn in the top-left corner
    padding: float = 0.3  # inches between the frame and its members
    header_height: float = 0.4  # inches reserved above members for the label


@dataclass(frozen=True)
class EdgeStyle:
    color: str = "#64748B"
    weight: float = 1.25  # points
    text: TextStyle = TextStyle(size=8.5, color="#475569")
    label_bg: str | None = "#FFFFFF"  # box behind edge labels so lines don't cross text
    corner: float = 0.08  # rounded corners on right-angle routes, inches


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    background: str  # page color
    title: TextStyle
    subtitle: TextStyle
    nodes: dict[str, ShapeStyle]  # by category
    groups: dict[str, GroupStyle]  # by GroupKind
    edge: EdgeStyle
    accent: str  # emphasis border and legend highlights
    secondary: TextStyle  # technology / description lines inside nodes
    dark: bool = False
    legend: ShapeStyle = field(default_factory=lambda: ShapeStyle(fill="#FFFFFF", line="#CBD5E1", rounding=0.06))

    def node_style(self, category: str) -> ShapeStyle:
        return self.nodes.get(category) or self.nodes["generic"]

    def group_style(self, kind: str, depth: int = 0) -> GroupStyle:
        """Style for a group; nested generic groups get a slightly lighter look per level."""
        return self.groups.get(kind) or self.groups["generic"]


def _node(fill: str, line: str, text: str = "#0F172A", rounding: float = 0.08, font: str = "Segoe UI",
          weight: float = 1.0, size: float = 10.0, bold: bool = True) -> ShapeStyle:
    return ShapeStyle(fill=fill, line=line, line_weight=weight, rounding=rounding,
                      text=TextStyle(font=font, size=size, color=text, bold=bold))


def _group(fill: str | None, line: str, header: str, pattern: LinePattern = "solid", font: str = "Segoe UI",
           weight: float = 1.0, rounding: float = 0.1, size: float = 10.0) -> GroupStyle:
    return GroupStyle(
        shape=ShapeStyle(fill=fill, line=line, line_weight=weight, line_pattern=pattern, rounding=rounding,
                         text=TextStyle(font=font, size=size, color=header, bold=True)),
        header=TextStyle(font=font, size=size, color=header, bold=True),
    )


def _groups(font: str, base_fill: str, base_line: str, header: str, **overrides: GroupStyle) -> dict[str, GroupStyle]:
    g = _group(base_fill, base_line, header, font=font)
    out = {k: g for k in (
        "generic", "tier", "system", "boundary", "cloud", "region", "zone", "network",
        "subnet", "cluster", "environment", "lane", "external",
    )}
    out.update(overrides)
    return out


# --- Professional: neutral slate with soft category tints (the default) -------------------
_F = "Segoe UI"
PROFESSIONAL = Theme(
    name="professional",
    description="Clean light theme with soft category tints. Good for any audience.",
    background="#FFFFFF",
    title=TextStyle(_F, 20, "#0F172A", bold=True),
    subtitle=TextStyle(_F, 11, "#64748B"),
    nodes={
        "terminal": _node("#E0E7FF", "#6366F1", rounding=0.3),
        "flow": _node("#EFF6FF", "#3B82F6"),
        "decision": _node("#FEF3C7", "#D97706", rounding=0),
        "data": _node("#ECFDF5", "#10B981"),
        "compute": _node("#EFF6FF", "#3B82F6"),
        "integration": _node("#F5F3FF", "#8B5CF6"),
        "client": _node("#F0F9FF", "#0EA5E9"),
        "person": _node("#F8FAFC", "#475569"),
        "external": _node("#F1F5F9", "#94A3B8"),
        "network": _node("#FFF7ED", "#F97316"),
        "security": _node("#FEF2F2", "#EF4444"),
        "org": _node("#EEF2FF", "#6366F1"),
        "entity": _node("#F8FAFC", "#64748B", rounding=0.04),
        "note": _node("#FEFCE8", "#EAB308", bold=False, rounding=0),
        "generic": _node("#FFFFFF", "#94A3B8"),
    },
    groups=_groups(
        _F, "#F8FAFC", "#CBD5E1", "#334155",
        boundary=_group(None, "#EF4444", "#B91C1C", "dashed"),
        external=_group("#F1F5F9", "#94A3B8", "#475569", "dashed"),
        environment=_group("#F8FAFC", "#64748B", "#334155"),
        region=_group(None, "#0EA5E9", "#0369A1", "dashed"),
        network=_group("#F0FDF4", "#22C55E", "#15803D"),
        subnet=_group("#FFFFFF", "#86EFAC", "#166534", "dashed"),
        cluster=_group("#EFF6FF", "#93C5FD", "#1D4ED8"),
        lane=_group("#FFFFFF", "#CBD5E1", "#334155", rounding=0),
    ),
    edge=EdgeStyle(),
    accent="#2563EB",
    secondary=TextStyle(_F, 8.5, "#475569"),
)

# --- Azure: Microsoft Fluent palette, mirrors Azure Architecture Center diagrams ---------
AZURE = Theme(
    name="azure",
    description="Microsoft Fluent palette in the style of Azure Architecture Center diagrams.",
    background="#FFFFFF",
    title=TextStyle(_F, 20, "#1B1A19", bold=True),
    subtitle=TextStyle(_F, 11, "#605E5C"),
    nodes={
        **PROFESSIONAL.nodes,
        "compute": _node("#FFFFFF", "#0078D4", "#1B1A19"),
        "flow": _node("#FFFFFF", "#0078D4", "#1B1A19"),
        "data": _node("#FFFFFF", "#0078D4", "#1B1A19"),
        "integration": _node("#FFFFFF", "#0078D4", "#1B1A19"),
        "security": _node("#FFFFFF", "#A4262C", "#1B1A19"),
        "generic": _node("#FFFFFF", "#8A8886", "#1B1A19"),
    },
    groups=_groups(
        _F, "#F3F2F1", "#C8C6C4", "#323130",
        cloud=_group(None, "#0078D4", "#0078D4", weight=1.5),
        region=_group(None, "#0078D4", "#005A9E", "dashed"),
        network=_group("#F3F9FD", "#0078D4", "#005A9E"),
        subnet=_group("#FFFFFF", "#6CB8F6", "#005A9E", "dashed"),
        boundary=_group(None, "#A4262C", "#A4262C", "dashed"),
        cluster=_group("#F3F9FD", "#6CB8F6", "#005A9E"),
        external=_group("#FAF9F8", "#A19F9D", "#605E5C", "dashed"),
    ),
    edge=EdgeStyle(color="#605E5C", text=TextStyle(_F, 8.5, "#323130")),
    accent="#0078D4",
    secondary=TextStyle(_F, 8.5, "#605E5C"),
)

# --- AWS: AWS Architecture Icons group conventions ---------------------------------------
_A = "Arial"
AWS = Theme(
    name="aws",
    description="AWS architecture conventions: AWS Cloud, Region, VPC and subnet groups.",
    background="#FFFFFF",
    title=TextStyle(_A, 20, "#232F3E", bold=True),
    subtitle=TextStyle(_A, 11, "#545B64"),
    nodes={
        **{k: replace(v, text=replace(v.text, font=_A)) for k, v in PROFESSIONAL.nodes.items()},
        "compute": _node("#FFFFFF", "#ED7100", "#232F3E", font=_A),
        "data": _node("#FFFFFF", "#C925D1", "#232F3E", font=_A),
        "integration": _node("#FFFFFF", "#E7157B", "#232F3E", font=_A),
        "network": _node("#FFFFFF", "#8C4FFF", "#232F3E", font=_A),
        "security": _node("#FFFFFF", "#DD344C", "#232F3E", font=_A),
    },
    groups=_groups(
        _A, "#FFFFFF", "#7D8998", "#232F3E",
        cloud=_group(None, "#232F3E", "#232F3E", font=_A, rounding=0, weight=1.5),
        region=_group(None, "#00A4A6", "#007D7F", "dashed", font=_A, rounding=0),
        zone=_group(None, "#00A4A6", "#007D7F", "dashed", font=_A, rounding=0),
        network=_group(None, "#8C4FFF", "#8C4FFF", font=_A, rounding=0),
        subnet=_group("#F2F6E8", "#7AA116", "#248814", font=_A, rounding=0),
        cluster=_group(None, "#ED7100", "#ED7100", "dashed", font=_A, rounding=0),
        boundary=_group(None, "#DD344C", "#DD344C", "dashed", font=_A, rounding=0),
        external=_group("#F2F3F3", "#7D8998", "#545B64", "dashed", font=_A, rounding=0),
    ),
    edge=EdgeStyle(color="#545B64", text=TextStyle(_A, 8.5, "#232F3E")),
    accent="#FF9900",
    secondary=TextStyle(_A, 8.5, "#545B64"),
)

# --- GCP: Google Cloud palette ------------------------------------------------------------
GCP = Theme(
    name="gcp",
    description="Google Cloud palette with project, region and VPC groups.",
    background="#FFFFFF",
    title=TextStyle(_A, 20, "#202124", bold=True),
    subtitle=TextStyle(_A, 11, "#5F6368"),
    nodes={
        **{k: replace(v, text=replace(v.text, font=_A)) for k, v in PROFESSIONAL.nodes.items()},
        "compute": _node("#FFFFFF", "#4285F4", "#202124", font=_A),
        "data": _node("#FFFFFF", "#34A853", "#202124", font=_A),
        "integration": _node("#FFFFFF", "#A142F4", "#202124", font=_A),
        "network": _node("#FFFFFF", "#FBBC04", "#202124", font=_A),
        "security": _node("#FFFFFF", "#EA4335", "#202124", font=_A),
    },
    groups=_groups(
        _A, "#F8F9FA", "#DADCE0", "#3C4043",
        cloud=_group("#F1F3F4", "#BDC1C6", "#3C4043", font=_A),
        region=_group("#FFFFFF", "#4285F4", "#1967D2", "dashed", font=_A),
        network=_group("#E8F0FE", "#4285F4", "#1967D2", font=_A),
        subnet=_group("#FFFFFF", "#8AB4F8", "#1967D2", "dashed", font=_A),
        cluster=_group("#E6F4EA", "#34A853", "#188038", font=_A),
        boundary=_group(None, "#EA4335", "#C5221F", "dashed", font=_A),
    ),
    edge=EdgeStyle(color="#5F6368", text=TextStyle(_A, 8.5, "#3C4043")),
    accent="#4285F4",
    secondary=TextStyle(_A, 8.5, "#5F6368"),
)

# --- C4: Simon Brown's C4 model colors ----------------------------------------------------
_W = "#FFFFFF"
C4 = Theme(
    name="c4",
    description="C4 model colors: people dark blue, systems blue, external grey, white text.",
    background="#FFFFFF",
    title=TextStyle(_F, 20, "#0B2545", bold=True),
    subtitle=TextStyle(_F, 11, "#5C6B7A"),
    nodes={
        **PROFESSIONAL.nodes,
        "person": _node("#08427B", "#073B6F", _W, rounding=0.3),
        "compute": _node("#438DD5", "#3C7FC0", _W),
        "flow": _node("#438DD5", "#3C7FC0", _W),
        "client": _node("#438DD5", "#3C7FC0", _W),
        "integration": _node("#438DD5", "#3C7FC0", _W),
        "data": _node("#438DD5", "#3C7FC0", _W),
        "external": _node("#999999", "#8A8A8A", _W),
        "generic": _node("#1168BD", "#0F5EAA", _W),
    },
    groups=_groups(
        _F, None, "#444444", "#444444",
        **{k: _group(None, "#444444", "#444444", "dashed") for k in ("generic", "system", "boundary", "tier")},
        external=_group(None, "#999999", "#666666", "dashed"),
    ),
    edge=EdgeStyle(color="#707070", text=TextStyle(_F, 8.5, "#404040")),
    accent="#1168BD",
    secondary=TextStyle(_F, 8.5, "#E8F1FB"),
)

# --- Blueprint: dark navy, white lines ----------------------------------------------------
_B = "#E2E8F0"
BLUEPRINT = Theme(
    name="blueprint",
    description="Dark navy blueprint with crisp light lines. Great on screens and slides.",
    background="#0B1F3A",
    title=TextStyle(_F, 20, "#F8FAFC", bold=True),
    subtitle=TextStyle(_F, 11, "#93C5FD"),
    nodes={c: _node("#12305A", "#93C5FD", "#F8FAFC") for c in CATEGORIES}
    | {
        "decision": _node("#12305A", "#FBBF24", "#F8FAFC", rounding=0),
        "data": _node("#12305A", "#6EE7B7", "#F8FAFC"),
        "integration": _node("#12305A", "#C4B5FD", "#F8FAFC"),
        "security": _node("#12305A", "#FCA5A5", "#F8FAFC"),
        "note": _node("#1E3A5F", "#FDE68A", "#FEF9C3", bold=False, rounding=0),
    },
    groups=_groups(_F, "#0F2747", "#3B82F6", "#BFDBFE",
                   boundary=_group(None, "#F87171", "#FCA5A5", "dashed"),
                   subnet=_group(None, "#60A5FA", "#BFDBFE", "dashed")),
    edge=EdgeStyle(color="#93C5FD", text=TextStyle(_F, 8.5, _B), label_bg="#0B1F3A"),
    accent="#FBBF24",
    secondary=TextStyle(_F, 8.5, "#BFDBFE"),
    dark=True,
    legend=ShapeStyle(fill="#0F2747", line="#3B82F6", rounding=0.06, text=TextStyle(_F, 9, _B)),
)

# --- Dark: slate dark mode ----------------------------------------------------------------
DARK = Theme(
    name="dark",
    description="Slate dark mode with vivid category accents.",
    background="#0F172A",
    title=TextStyle(_F, 20, "#F1F5F9", bold=True),
    subtitle=TextStyle(_F, 11, "#94A3B8"),
    nodes={c: _node("#1E293B", "#64748B", "#F1F5F9") for c in CATEGORIES}
    | {
        "flow": _node("#1E293B", "#60A5FA", "#F1F5F9"),
        "compute": _node("#1E293B", "#60A5FA", "#F1F5F9"),
        "terminal": _node("#1E293B", "#818CF8", "#F1F5F9", rounding=0.3),
        "decision": _node("#1E293B", "#FBBF24", "#F1F5F9", rounding=0),
        "data": _node("#1E293B", "#34D399", "#F1F5F9"),
        "integration": _node("#1E293B", "#A78BFA", "#F1F5F9"),
        "client": _node("#1E293B", "#38BDF8", "#F1F5F9"),
        "network": _node("#1E293B", "#FB923C", "#F1F5F9"),
        "security": _node("#1E293B", "#F87171", "#F1F5F9"),
    },
    groups=_groups(_F, "#111C30", "#334155", "#CBD5E1",
                   boundary=_group(None, "#F87171", "#FCA5A5", "dashed")),
    edge=EdgeStyle(color="#94A3B8", text=TextStyle(_F, 8.5, "#CBD5E1"), label_bg="#0F172A"),
    accent="#38BDF8",
    secondary=TextStyle(_F, 8.5, "#94A3B8"),
    dark=True,
    legend=ShapeStyle(fill="#111C30", line="#334155", rounding=0.06, text=TextStyle(_F, 9, "#CBD5E1")),
)

# --- Monochrome: print friendly -----------------------------------------------------------
MONO = Theme(
    name="monochrome",
    description="Greyscale, print and photocopy friendly.",
    background="#FFFFFF",
    title=TextStyle(_F, 20, "#111111", bold=True),
    subtitle=TextStyle(_F, 11, "#555555"),
    nodes={c: _node("#FFFFFF", "#333333", "#111111") for c in CATEGORIES}
    | {
        "decision": _node("#F2F2F2", "#333333", "#111111", rounding=0),
        "terminal": _node("#E6E6E6", "#333333", "#111111", rounding=0.3),
        "data": _node("#F2F2F2", "#333333", "#111111"),
        "note": _node("#FAFAFA", "#999999", "#333333", bold=False, rounding=0),
    },
    groups=_groups(_F, "#FAFAFA", "#999999", "#333333",
                   boundary=_group(None, "#333333", "#333333", "dashed")),
    edge=EdgeStyle(color="#333333", text=TextStyle(_F, 8.5, "#333333")),
    accent="#000000",
    secondary=TextStyle(_F, 8.5, "#555555"),
)

THEMES: dict[str, Theme] = {t.name: t for t in (PROFESSIONAL, AZURE, AWS, GCP, C4, BLUEPRINT, DARK, MONO)}
_THEME_ALIASES = {"default": "professional", "light": "professional", "mono": "monochrome", "google": "gcp"}


def get_theme(name: str) -> Theme:
    key = _THEME_ALIASES.get(name.strip().lower(), name.strip().lower())
    if key not in THEMES:
        raise ValueError(f"unknown theme {name!r}; choose one of {sorted(THEMES)}")
    return THEMES[key]


# --- Text casing --------------------------------------------------------------------------

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


# --- Sizing ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeSize:
    """Footprint the layout reserves for a node, and where the Visio shape sits inside it."""

    w: float
    h: float
    shape_w: float
    shape_h: float
    dy: float = 0.0  # shape center = footprint center + (0, dy); icons sit above their label


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


GEOMETRY_MIN = {  # (min width, min height) in inches per catalog geometry
    "rect": (1.6, 0.75),
    "rounded": (1.6, 0.75),
    "terminator": (1.5, 0.6),
    "decision": (1.7, 1.1),
    "parallelogram": (1.8, 0.75),
    "document": (1.6, 0.85),
    "cylinder": (1.2, 1.0),
    "queue": (1.7, 0.75),
    "hexagon": (1.7, 0.8),
    "ellipse": (1.5, 0.8),
    "circle": (0.9, 0.9),
    "cloud": (1.8, 1.1),
    "person": (1.2, 1.2),
    "note": (1.6, 0.8),
    "entity": (1.8, 0.9),
    "subprocess": (1.7, 0.75),
    "trapezoid": (1.7, 0.75),
    "icon": (0.7, 0.7),
}
ICON_SIZE = 0.7  # inches, square icon masters (cloud services, network gear, people)


def node_size(geometry: str, label: str, technology: str = "", description: str = "",
              theme: Theme = PROFESSIONAL, category: str = "generic") -> NodeSize:
    """Size a node so its text fits on at most a few lines, never smaller than the geometry minimum."""
    st = theme.node_style(category).text
    sec = theme.secondary
    if geometry in ("icon", "person"):
        # icon on top, label (and tech) below it, inside a footprint wide enough for the text
        max_w = 1.7
        lines = wrap(label, st.size, max_w, st.bold)
        tlines = wrap(f"[{technology}]", sec.size, max_w) if technology else []
        text_h = len(lines) * st.size * 1.25 / 72 + len(tlines) * sec.size * 1.25 / 72
        w = max(ICON_SIZE + 0.4, min(max_w, max(text_width(s, st.size, st.bold) for s in lines + [""])) + 0.25)
        h = ICON_SIZE + 0.12 + text_h
        return NodeSize(w=round(w, 2), h=round(h, 2), shape_w=ICON_SIZE, shape_h=ICON_SIZE,
                        dy=round((h - ICON_SIZE) / 2, 3))
    min_w, min_h = GEOMETRY_MIN.get(geometry, (1.6, 0.75))
    inner = {"decision": 0.55, "hexagon": 0.75, "ellipse": 0.7, "circle": 0.7, "cloud": 0.6,
             "parallelogram": 0.75, "trapezoid": 0.75}.get(geometry, 0.88)
    max_w = 2.6
    text_w = max_w * inner
    lines = wrap(label, st.size, text_w, st.bold)
    widest = max(text_width(s, st.size, st.bold) for s in lines)
    extra: list[str] = []
    if technology:
        extra += wrap(f"[{technology}]", sec.size, text_w)
    if description:
        extra += wrap(description, sec.size, text_w)[:3]
    widest = max([widest] + [text_width(s, sec.size) for s in extra])
    text_h = len(lines) * st.size * 1.3 / 72 + len(extra) * sec.size * 1.3 / 72
    w = max(min_w, min(max_w, widest / inner + 0.3))
    h = max(min_h, text_h / (inner if geometry in ("decision", "ellipse", "circle", "hexagon") else 1) + 0.3)
    if geometry == "circle":
        w = h = max(w, h)
    w, h = math.ceil(w * 8 - 1e-6) / 8, math.ceil(h * 8 - 1e-6) / 8  # snap up to 1/8 inch so rows line up
    return NodeSize(w=w, h=h, shape_w=w, shape_h=h)
