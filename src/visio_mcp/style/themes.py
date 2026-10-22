"""Built-in themes, the THEMES registry and get_theme."""

from __future__ import annotations

from dataclasses import replace

from visio_mcp.style.model import (
    CATEGORIES,
    EdgeStyle,
    GroupStyle,
    LinePattern,
    ShapeStyle,
    TextStyle,
    Theme,
)


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
