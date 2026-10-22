"""The catalog data types: Shape, Kind and Resolved."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Shape:
    stencil: str  # built-in stencil file name, e.g. "BASFLO_U.VSSX"
    master: str  # universal master name (NameU), e.g. "Process"


@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    candidates: tuple[Shape, ...]  # tried in order; first available wins
    category: str = "generic"  # style.CATEGORIES: picks the theme style
    geometry: str = "rect"  # style.GEOMETRY_MIN key: how non-Visio renderers draw it
    provider: str | None = None  # 'azure' | 'aws' | 'gcp' for cloud service kinds
    base: str | None = None  # generic kind to fall back to when no provider master exists
    glyph: str = ""  # 1-3 chars drawn inside the tile when there is no real icon (e.g. 'λ', 'SQL')


@dataclass(frozen=True)
class Resolved:
    shape: Shape
    warning: str | None  # set when the kind is unknown or we fell back
    kind: Kind | None = None  # the resolved kind (None when unknown)
    icon: bool = False  # the master is an icon: keep its colors, label sits below it


FALLBACK = Shape("BASIC_U.VSSX", "Rectangle")

FALLBACK = Shape("BASIC_U.VSSX", "Rectangle")
