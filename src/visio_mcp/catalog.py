"""Semantic shape kinds -> Visio stencil masters.  (F1: implement)"""

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
    fill: str | None = None  # default '#RRGGBB'


@dataclass(frozen=True)
class Resolved:
    shape: Shape
    fill: str | None
    warning: str | None  # set when the kind is unknown or we fell back


FALLBACK = Shape("BASIC_U.VSSX", "Rectangle")


def kinds() -> dict[str, Kind]:
    """All known kinds, keyed by name."""
    raise NotImplementedError


def resolve(kind: str, has_master: Callable[[str, str], bool]) -> Resolved:
    """Pick the first available candidate for kind; fall back to FALLBACK with a warning."""
    raise NotImplementedError
