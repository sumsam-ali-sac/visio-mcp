"""Find the installed official icon for a cloud kind, and explain how it matched."""

from __future__ import annotations

from pathlib import Path

from visio_mcp import catalog
from visio_mcp.icons.index import load_index
from visio_mcp.icons.names import ICON_NAMES, normalize, squash, tokens
from visio_mcp.icons.paths import provider_dir
from visio_mcp.icons.providers import IMAGE_EXTS, PROVIDERS


def installed(provider: str) -> bool:
    idx = load_index(provider)
    return bool(idx and idx["icons"])


def missing_for(kind_names: list[str] | tuple[str, ...]) -> list[str]:
    """Providers used by these kinds whose icon pack is not installed (catalog order)."""
    used = []
    for name in kind_names:
        k = catalog.lookup(name)
        if k and k.provider and k.provider not in used:
            used.append(k.provider)
    return [p for p in PROVIDERS if p in used and not installed(p)]


def _match(idx: dict, name: str) -> str | None:
    key = normalize(name)
    if key in idx["icons"]:
        return key
    return idx["_squashed"].get(squash(key))


def _fuzzy(idx: dict, words: set[str]) -> str | None:
    best, best_score = None, 0.0
    for key in idx["icons"]:
        t = tokens(key)
        inter = len(words & t)
        if not inter:
            continue
        score = inter / max(len(words), len(t))
        if score > best_score or (score == best_score and best is not None and len(key) < len(best)):
            best, best_score = key, score
    return best if best_score >= 0.5 else None


def explain(kind_name: str) -> tuple[str | None, str | None, str]:
    """(provider, matched icon key, how) where how is 'curated' | 'fuzzy' | 'none' | 'no-pack'."""
    k = catalog.lookup(kind_name)
    if k is None or not k.provider:
        return None, None, "none"
    idx = load_index(k.provider)
    if not idx:
        return k.provider, None, "no-pack"
    slug = k.name[len(k.provider) + 1:]
    for cand in ICON_NAMES.get(k.name, ()) + (slug,):
        hit = _match(idx, cand)
        if hit:
            return k.provider, hit, "curated"
    hit = _fuzzy(idx, tokens(normalize(slug)))
    return k.provider, hit, "fuzzy" if hit else "none"


def find(kind_name: str) -> Path | None:
    """The installed official icon for a cloud kind (None for generic kinds or no pack)."""
    k = catalog.lookup(kind_name)
    if k is None or not k.provider:
        return None
    _, key, _ = explain(k.name)
    if not key:
        return None
    idx = load_index(k.provider)
    assert idx is not None
    p = provider_dir(k.provider) / idx["icons"][key]
    return p if p.is_file() else None


def resolve_image(node_icon: str | None, kind_name: str) -> Path | None:
    """A custom Node.icon (existing .svg/.png) wins; else the kind's official icon, if installed."""
    if node_icon:
        p = Path(node_icon).expanduser()
        if p.suffix.lower() in IMAGE_EXTS and p.is_file():
            return p.resolve()
        return None
    return find(kind_name)
