"""Resolve each node's catalog kind, Visio master, icon image, geometry and footprint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from visio_mcp import catalog, icons
from visio_mcp.catalog import Shape
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import NodeSize, Theme, node_size

HasMaster = Callable[[str, str], bool]


@dataclass
class ResolvedNodes:
    kinds: dict[str, tuple[catalog.Kind | None, Shape | None, bool]] = field(default_factory=dict)  # kind, master, icon
    images: dict[str, Path | None] = field(default_factory=dict)
    geometries: dict[str, str] = field(default_factory=dict)
    sizes: dict[str, NodeSize] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def resolve_nodes(spec: DiagramSpec, theme: Theme, has_master: HasMaster | None) -> ResolvedNodes:
    """Resolve and size every node.

    has_master: the Visio backend's lookup, so kinds resolve to real stencil masters and
    icon masters get icon-sized footprints. None plans for the non-Visio renderers.
    """
    out = ResolvedNodes()
    warnings = out.warnings
    no_icon: dict[str, int] = {}  # provider -> cloud nodes drawn without an official icon
    for n in spec.nodes:
        kind = catalog.lookup(n.kind)
        master: Shape | None = None
        image = icons.resolve_image(n.icon, n.kind)
        if n.icon and image is None:
            warnings.append(f"icon for {n.id!r} not found or not .svg/.png: {n.icon}")
        if has_master is not None:
            r = catalog.resolve(n.kind, has_master)
            kind, master, icon = r.kind or kind, r.shape, r.icon
            # a real icon master from the kind's own stencil candidates beats the downloaded icon,
            # unless the spec names a custom icon; generic stand-ins (base kind, rectangle) lose
            own_icon = icon and kind is not None and master in kind.candidates
            if image is not None and (n.icon or not own_icon):
                master, icon = None, True
            else:
                image = None
                if r.warning:
                    warnings.append(r.warning)
            if image is None and not own_icon and kind is not None and kind.provider:
                no_icon[kind.provider] = no_icon.get(kind.provider, 0) + 1
        else:
            icon = image is not None or bool(kind and kind.geometry in ("icon", "person"))
            if image is None and kind is not None and kind.provider:
                no_icon[kind.provider] = no_icon.get(kind.provider, 0) + 1
        category = kind.category if kind else "generic"
        geometry = "icon" if image is not None else _geometry(kind, icon, has_master is not None)
        out.kinds[n.id] = (kind, master, icon)
        out.images[n.id] = image
        out.geometries[n.id] = geometry
        out.sizes[n.id] = node_size(geometry, n.label, n.technology, n.description, theme, category)
    if no_icon:
        count = sum(no_icon.values())
        names = ", ".join(icons.PROVIDER_NAMES[p] for p in icons.PROVIDERS if p in no_icon)
        warnings.append(f"{count} {names} service{'s' if count != 1 else ''} drawn without official icons; "
                        "install official icons: visio-ai icons install (MCP: install_icons)")
    return out


def _geometry(kind: catalog.Kind | None, icon: bool, visio: bool) -> str:
    """How the node is drawn. In Visio a non-icon master stands in for icon kinds, so use the
    geometry of the base kind it fell back to; without Visio icon kinds draw as glyph tiles."""
    if kind is None:
        return "rounded"
    if icon:
        return "person" if kind.geometry == "person" else "icon"
    if visio and kind.geometry in ("icon", "person"):
        base = kind
        while base.geometry in ("icon", "person") and base.base and (nxt := catalog.lookup(base.base)):
            base = nxt
        return base.geometry if base.geometry not in ("icon", "person") else "rounded"
    return kind.geometry
