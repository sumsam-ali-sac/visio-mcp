"""Semantic shape kinds -> Visio stencil masters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Shape:
    stencil: str  # built-in stencil file name, e.g. "BASFLO_U.VSSX"
    master: str  # universal master name (NameU), e.g. "Process"


@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    candidates: tuple[Shape, ...]  # tried in order; first available wins
    fill: str | None = None  # default '#RRGGBB' (legacy; themes style by category)
    category: str = "generic"  # style.CATEGORIES: picks the theme style
    geometry: str = "rect"  # style.GEOMETRY_MIN key: how non-Visio renderers draw it
    provider: str | None = None  # 'azure' | 'aws' | 'gcp' for cloud service kinds
    base: str | None = None  # generic kind to fall back to when no provider master exists
    glyph: str = ""  # 1-3 chars drawn inside the tile when there is no real icon (e.g. 'λ', 'SQL')


@dataclass(frozen=True)
class Resolved:
    shape: Shape
    fill: str | None
    warning: str | None  # set when the kind is unknown or we fell back
    kind: Kind | None = None  # the resolved kind (None when unknown)
    icon: bool = False  # the master is an icon: keep its colors, label sits below it


FALLBACK = Shape("BASIC_U.VSSX", "Rectangle")

# Light fills, one per category, so black text stays readable.
_FLOW = "#DCEBFF"
_SOFT = "#DDF3E4"
_NET = "#FFF1D6"
_ORG = "#EADCF8"
_ERD = "#E3E8EE"
_NOTE = "#FFF9C4"

_BASFLO = "BASFLO_U.VSSX"
_BASIC = "BASIC_U.VSSX"
_NETSYM = "NETSYM_U.VSSX"
_SERVER = "SERVER_U.VSSX"
_COMPS = "COMPS_U.VSSX"
_ORGCH = "ORGCH_U.VSSX"
_PEOPLE = "PEOPLE_U.VSSX"
_AZ_ENT = "AZUREENTERPRISE_U.VSSX"
_AZ_GEN = "AZUREGENERAL_U.VSSX"

# Plain geometric stencils take the kind's fill; icon stencils keep their own colors.
_FILLABLE = {_BASFLO, _BASIC, _ORGCH, "DBCHEN_U.VSSX", "WEBSIT_U.VSSX", "ANNOT_U.VSSX"}


def _k(name: str, description: str, fill: str | None, *shapes: tuple[str, str]) -> Kind:
    return Kind(name, description, tuple(Shape(s, m) for s, m in shapes), fill)


_KINDS: tuple[Kind, ...] = (
    # flowchart
    _k("process", "A step or action in a flow.", _FLOW, (_BASFLO, "Process")),
    _k("decision", "A yes/no or branching question.", _FLOW, (_BASFLO, "Decision")),
    _k("start", "Entry point of a flow (rounded terminator).", _FLOW, (_BASFLO, "Start/End")),
    _k("end", "Exit point of a flow (rounded terminator).", _FLOW, (_BASFLO, "Start/End")),
    _k("data", "Input or output data (parallelogram).", _FLOW, (_BASFLO, "Data"), (_BASIC, "Parallelogram")),
    _k("document", "A document or report.", _FLOW, (_BASFLO, "Document")),
    _k("subprocess", "A predefined process that is detailed elsewhere.", _FLOW, (_BASFLO, "Subprocess")),
    _k("manual", "A manual step done by a person.", _FLOW, (_BASIC, "Trapezoid")),
    # architecture / software
    _k(
        "database", "A database or data store (cylinder).", _SOFT,
        (_BASFLO, "Database"), (_NETSYM, "Relational database"), (_BASIC, "Can"),
    ),
    _k(
        "service", "A backend service, microservice or application component.", _SOFT,
        (_SERVER, "Application server"), (_BASIC, "Rounded Rectangle"),
    ),
    _k(
        "api", "An API or web service endpoint.", _SOFT,
        (_AZ_ENT, "XML Web Service"), ("DTLNET_U.VSSX", "XML Web Service"), (_BASIC, "Hexagon"),
    ),
    _k("webapp", "A web app, website or frontend page.", _SOFT, ("WEBSIT_U.VSSX", "Web page"), (_BASIC, "Rounded Rectangle")),
    _k("cache", "An in-memory cache such as Redis or Memcached.", _SOFT, (_AZ_GEN, "Cache"), ("AWSDB_U.VSSX", "Cache Node"), (_BASIC, "Can")),
    _k(
        "queue", "A message queue, event bus or broker.", _SOFT,
        (_AZ_ENT, "Queue, General"), (_AZ_GEN, "Storage Queue"), (_BASIC, "Parallelogram"),
    ),
    _k("storage", "Object, blob or file storage.", _SOFT, (_AZ_ENT, "Storage"), ("AWSSTORAGE_U.VSSX", "Storage"), (_BASIC, "Cube")),
    _k("function", "A serverless function.", _SOFT, ("AZURECOMPUTE_U.VSSX", "Function Apps"), ("AZURECLOUD_U.VSSX", "Azure Functions"), (_BASIC, "Octagon")),
    _k("gateway", "An API gateway or protocol gateway.", _SOFT, (_NETSYM, "Gateway"), (_AZ_ENT, "Gateway"), (_BASIC, "Hexagon")),
    _k("loadbalancer", "A load balancer spreading traffic across instances.", _SOFT, (_AZ_ENT, "Load Balancer"), (_BASIC, "Diamond")),
    _k("external", "An external system or third-party service outside your control.", _SOFT, (_BASFLO, "External Data")),
    _k("user", "A person or actor using the system.", _SOFT, (_PEOPLE, "User"), ("AZUREGENERALSYMBOLS_U.VSSX", "User")),
    _k("client", "A client application or browser.", _SOFT, (_AZ_GEN, "Browser"), (_COMPS, "PC")),
    _k("mobile", "A mobile device or app.", _SOFT, (_AZ_GEN, "Mobile"), (_AZ_ENT, "Phone"), (_COMPS, "PDA")),
    # network / infrastructure
    _k("server", "A generic server.", _NET, (_SERVER, "Server")),
    _k("router", "A network router.", _NET, (_NETSYM, "Router")),
    _k("switch", "A network switch.", _NET, (_NETSYM, "Workgroup switch")),
    _k("firewall", "A firewall.", _NET, (_AZ_ENT, "Firewall"), ("AWSGEN_U.VSSX", "Generic Firewall"), (_BASIC, "Pentagon")),
    _k("cloud", "A cloud or WAN network region.", _NET, ("NETLOC_U.VSSX", "Cloud"), (_AZ_ENT, "Cloud")),
    _k("internet", "The public internet.", _NET, (_AZ_ENT, "Internet"), ("AWSGEN_U.VSSX", "Internet alt1"), ("NETLOC_U.VSSX", "Cloud")),
    _k("pc", "A desktop or laptop computer.", _NET, (_COMPS, "PC"), (_COMPS, "Laptop computer")),
    # org chart
    _k("executive", "A top executive in an org chart.", _ORG, (_ORGCH, "Executive")),
    _k("manager", "A manager in an org chart.", _ORG, (_ORGCH, "Manager")),
    _k("position", "An employee or position in an org chart.", _ORG, (_ORGCH, "Position")),
    # ERD
    # Chen entity is one shape; the Crow's Foot entity spawns attribute-row shapes that layout scatters.
    _k("entity", "A database entity (table) in an ER diagram.", _ERD, ("DBCHEN_U.VSSX", "Entity")),
    # generic
    _k("box", "A plain rectangle.", None, (_BASIC, "Rectangle")),
    _k("ellipse", "A plain ellipse.", None, (_BASIC, "Ellipse")),
    _k("note", "A sticky note or free text annotation.", _NOTE, (_BASIC, "Single Snip Corner Rectangle"), ("ANNOT_U.VSSX", "Note symbol")),
)

_BY_NAME: dict[str, Kind] = {k.name: k for k in _KINDS}

_ALIASES = {
    "db": "database",
    "terminator": "start",
    "io": "data",
    "input": "data",
    "output": "data",
    "actor": "user",
    "person": "user",
    "frontend": "webapp",
    "web": "webapp",
    "browser": "client",
    "app": "service",
    "microservice": "service",
    "bus": "queue",
    "blob": "storage",
    "lambda": "function",
    "serverless": "function",
    "lb": "loadbalancer",
    "load_balancer": "loadbalancer",
    "laptop": "pc",
    "computer": "pc",
    "employee": "position",
    "table": "entity",
    "rectangle": "box",
    "text": "note",
}


def kinds() -> dict[str, Kind]:
    """All known kinds, keyed by name."""
    return dict(_BY_NAME)


def resolve(kind: str, has_master: Callable[[str, str], bool]) -> Resolved:
    """Pick the first available candidate for kind; fall back to FALLBACK with a warning."""
    key = kind.strip().lower()
    key = _ALIASES.get(key, key)
    k = _BY_NAME.get(key)
    if k is None:
        return Resolved(FALLBACK, None, f"unknown kind '{kind}', drew a rectangle (see list_kinds)")
    for shape in k.candidates:
        if has_master(shape.stencil, shape.master):
            return Resolved(shape, k.fill if shape.stencil in _FILLABLE else None, None)
    return Resolved(FALLBACK, k.fill, f"no stencil master available for kind '{kind}', drew a rectangle")


def lookup(kind: str) -> Kind | None:
    """The Kind for a name or alias, or None when unknown."""
    key = kind.strip().lower()
    return _BY_NAME.get(_ALIASES.get(key, key))
