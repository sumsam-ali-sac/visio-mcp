"""Look up kinds by name or alias, suggest near misses, and resolve a kind to an available stencil master."""

from __future__ import annotations

import difflib
from collections.abc import Callable

from visio_mcp.catalog.aliases import ALIASES
from visio_mcp.catalog.model import FALLBACK, Kind, Resolved, Shape
from visio_mcp.catalog.registry import BY_NAME
from visio_mcp.catalog.stencils import FILLABLE


def lookup(kind: str) -> Kind | None:
    """The Kind for a name or alias (exact, no fuzzy matching), or None when unknown."""
    key = kind.strip().lower()
    return BY_NAME.get(ALIASES.get(key, key))


def suggest(kind: str, n: int = 3) -> list[str]:
    """Close kind names for an unknown kind: prefix matches first, then difflib matches."""
    key = kind.strip().lower()
    names = list(BY_NAME) + list(ALIASES)
    out = [x for x in names if key and (x.startswith(key) or (len(key) >= 3 and key in x))]
    out += difflib.get_close_matches(key, names, n=n, cutoff=0.6)
    seen: list[str] = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen[:n]


def _pick(k: Kind, has_master: Callable[[str, str], bool], depth: int = 0) -> tuple[Shape, bool] | None:
    """First available master for k (own candidates, then its base chain) and whether it is an icon."""
    for shape in k.candidates:
        if has_master(shape.stencil, shape.master):
            return shape, shape.stencil not in FILLABLE
    base = BY_NAME.get(k.base) if k.base and depth < 8 else None
    return _pick(base, has_master, depth + 1) if base else None


def resolve(kind: str, has_master: Callable[[str, str], bool]) -> Resolved:
    """Pick the first available candidate for kind (then its base kind); else FALLBACK with a warning."""
    k = lookup(kind)
    if k is None:
        hint = suggest(kind)
        tip = f"; did you mean {', '.join(repr(h) for h in hint)}?" if hint else ""
        return Resolved(FALLBACK, f"unknown kind '{kind}', drew a rectangle{tip} (see list_kinds)")
    picked = _pick(k, has_master)
    if picked:
        shape, icon = picked
        return Resolved(shape, None, k, icon)
    return Resolved(FALLBACK, f"no stencil master available for kind '{kind}', drew a rectangle", k)
