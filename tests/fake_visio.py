"""In-memory VisioBackend for tests. Records calls and lays shapes out on a simple grid."""

from __future__ import annotations

import math
from pathlib import Path

from visio_mcp.backend import ShapeInfo

DEFAULT_MASTERS = {
    "BASIC_U.VSSX": ["Rectangle", "Ellipse", "Rounded Rectangle", "Diamond"],
    "BASFLO_U.VSSX": ["Process", "Decision", "Start/End", "Data", "Document", "Database"],
}


class FakeVisio:
    def __init__(self, masters: dict[str, list[str]] | None = None) -> None:
        self.masters = masters if masters is not None else DEFAULT_MASTERS
        self.title: str | None = None
        self.items: dict[str, ShapeInfo] = {}
        self.fills: dict[str, str] = {}
        self.edges: dict[str, dict] = {}
        self.containers: dict[str, list[str]] = {}
        self.layouts: list[str] = []
        self.files: list[str] = []

    # documents
    def new_document(self, title: str) -> None:
        self.__init__(self.masters)
        self.title = title

    def open_document(self, path: str) -> None:
        self.new_document(Path(path).stem)

    def save(self, path: str) -> str:
        p = str(Path(path).resolve())
        self.files.append(p)
        return p

    def export(self, path: str) -> str:
        return self.save(path)

    # stencils
    def list_stencils(self) -> list[str]:
        return sorted(self.masters)

    def list_masters(self, stencil: str) -> list[str]:
        return list(self.masters.get(stencil.upper(), []))

    def has_master(self, stencil: str, master: str) -> bool:
        return master in self.masters.get(stencil.upper(), [])

    # shapes
    def drop_shape(self, name, stencil, master, x, y, width=None, height=None) -> None:
        if not self.has_master(stencil, master):
            raise KeyError(f"no master {master!r} in {stencil!r}")
        if name in self.items:
            raise KeyError(f"duplicate shape name {name!r}")
        self.items[name] = ShapeInfo(name, "", master, x, y, width or 1.0, height or 0.75)

    def set_text(self, name: str, text: str) -> None:
        self.items[name].text = text

    def set_fill(self, name: str, color: str) -> None:
        self._get(name)
        self.fills[name] = color

    def connect(self, name, source, target, label="", pattern="solid", arrow="end") -> None:
        self._get(source), self._get(target)
        self.edges[name] = dict(source=source, target=target, label=label, pattern=pattern, arrow=arrow)
        self.items[name] = ShapeInfo(name, label, "Dynamic connector", 0, 0, 0, 0, is_connector=True)

    def add_container(self, name: str, label: str, members: list[str]) -> None:
        boxes = [self._get(m) for m in members]
        left = min(b.x - b.width / 2 for b in boxes) - 0.25
        right = max(b.x + b.width / 2 for b in boxes) + 0.25
        bottom = min(b.y - b.height / 2 for b in boxes) - 0.25
        top = max(b.y + b.height / 2 for b in boxes) + 0.5
        self.containers[name] = list(members)
        self.items[name] = ShapeInfo(
            name, label, "Container", (left + right) / 2, (bottom + top) / 2,
            right - left, top - bottom, is_container=True,
        )

    def move(self, name: str, x: float, y: float) -> None:
        s = self._get(name)
        s.x, s.y = x, y

    def delete(self, name: str) -> None:
        self._get(name)
        del self.items[name]
        self.edges.pop(name, None)
        self.containers.pop(name, None)
        for e in [k for k, v in self.edges.items() if name in (v["source"], v["target"])]:
            del self.edges[e]
            del self.items[e]

    def shapes(self) -> list[ShapeInfo]:
        return list(self.items.values())

    # page
    def layout(self, preset: str) -> None:
        self.layouts.append(preset)
        if preset == "none":
            return
        boxes = [s for s in self.items.values() if not (s.is_connector or s.is_container)]
        cols = max(1, math.ceil(math.sqrt(len(boxes))))
        for i, s in enumerate(boxes):
            s.x, s.y = 1 + (i % cols) * 2.0, 1 + (i // cols) * 1.5

    def _get(self, name: str) -> ShapeInfo:
        if name not in self.items:
            raise KeyError(f"no shape named {name!r}")
        return self.items[name]
