"""In-memory VisioBackend for tests: records every call and keeps a simple model of the page."""

from __future__ import annotations

from pathlib import Path

from visio_mcp.output.visio.backend import ShapeInfo
from visio_mcp.style import TextRun
from visio_mcp.style import EdgeStyle, GroupStyle, ShapeStyle

DEFAULT_MASTERS = {
    "BASIC_U.VSSX": ["Rectangle", "Ellipse", "Rounded Rectangle", "Diamond"],
    "BASFLO_U.VSSX": ["Process", "Decision", "Start/End", "Data", "Document", "Database"],
}
BACKGROUND = "__background"


class FakeVisio:
    def __init__(self, masters: dict[str, list[str]] | None = None) -> None:
        self.masters = masters if masters is not None else DEFAULT_MASTERS
        self.title: str | None = None
        self.items: dict[str, ShapeInfo] = {}
        self.fills: dict[str, str] = {}
        self.edges: dict[str, dict] = {}
        self.containers: dict[str, list[str]] = {}
        self.files: list[str] = []
        self.runs: dict[str, list[TextRun]] = {}  # rich text per shape
        self.styles: dict[str, dict] = {}  # name -> dict(style, keep_fill, label_below)
        self.edge_styles: dict[str, dict] = {}  # name -> dict(style, color)
        self.container_styles: dict[str, GroupStyle | None] = {}
        self.container_bounds: dict[str, tuple[float, float, float, float] | None] = {}
        self.boxes: dict[str, ShapeStyle] = {}
        self.texts: dict[str, dict] = {}  # name -> dict(runs, align)
        self.lines: dict[str, dict] = {}  # name -> dict(points, style, pattern, arrow)
        self.page: dict = dict(width=8.5, height=11.0, background=None)
        self.z_order: list[str] = []  # back to front
        self.presented = 0
        self.images: dict[str, str] = {}  # name -> imported icon file

    # documents
    def new_document(self, title: str) -> None:
        self.__init__(self.masters)
        self.title = title

    def open_document(self, path: str) -> None:
        self.new_document(Path(path).stem)

    def save(self, path: str) -> str:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake")
        self.files.append(str(p))
        return str(p)

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
        self._add(ShapeInfo(name, "", master, x, y, width or 1.0, height or 0.75))

    def drop_image(self, name: str, path: str, x: float, y: float, width: float, height: float) -> None:
        if not Path(path).is_file():
            raise OSError(f"no such image {path!r}")
        self._add(ShapeInfo(name, "", "Image", x, y, width, height))
        self.images[name] = path

    def set_text(self, name: str, text: str) -> None:
        self._get(name).text = text
        self.runs.pop(name, None)

    def set_rich_text(self, name: str, runs: list[TextRun]) -> None:
        self._get(name).text = "".join(r.text for r in runs)
        self.runs[name] = list(runs)

    def set_fill(self, name: str, color: str) -> None:
        self._get(name)
        self.fills[name] = color

    def style_shape(self, name: str, style: ShapeStyle, keep_fill: bool = False, label_below: bool = False) -> None:
        self._get(name)
        self.styles[name] = dict(style=style, keep_fill=keep_fill, label_below=label_below)

    def connect(self, name, source, target, label="", pattern="solid", arrow="end") -> None:
        self._get(source), self._get(target)
        self._add(ShapeInfo(name, label, "Dynamic connector", 0, 0, 0, 0, is_connector=True))
        self.edges[name] = dict(source=source, target=target, label=label, pattern=pattern, arrow=arrow)

    def style_connector(self, name: str, style: EdgeStyle, color: str | None = None) -> None:
        self._get(name)
        self.edge_styles[name] = dict(style=style, color=color or style.color)

    def add_container(self, name: str, label: str, members: list[str],
                      style: GroupStyle | None = None, bounds: tuple[float, float, float, float] | None = None) -> None:
        boxes = [self._get(m) for m in members]
        if bounds is not None:
            x, y, w, h = bounds
        else:
            pad = style.padding if style else 0.25
            head = style.header_height if style else 0.25
            left = min(b.x - b.width / 2 for b in boxes) - pad
            right = max(b.x + b.width / 2 for b in boxes) + pad
            bottom = min(b.y - b.height / 2 for b in boxes) - pad
            top = max(b.y + b.height / 2 for b in boxes) + pad + head
            x, y, w, h = (left + right) / 2, (bottom + top) / 2, right - left, top - bottom
        self._add(ShapeInfo(name, label, "Container", x, y, w, h, is_container=True))
        self.containers[name] = list(members)
        self.container_styles[name] = style
        self.container_bounds[name] = bounds
        self._to_back(name)

    def add_box(self, name: str, x: float, y: float, width: float, height: float, style: ShapeStyle) -> None:
        self._add(ShapeInfo(name, "", None, x, y, width, height))
        self.boxes[name] = style

    def add_text(self, name, x, y, width, height, runs: list[TextRun], align="left") -> None:
        self._add(ShapeInfo(name, "".join(r.text for r in runs), None, x, y, width, height))
        self.runs[name] = list(runs)
        self.texts[name] = dict(runs=list(runs), align=align)

    def add_line(self, name, x1, y1, x2, y2, style: EdgeStyle, pattern="solid", arrow="end") -> None:
        self._add(ShapeInfo(name, "", None, (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1), abs(y2 - y1),
                            is_connector=True))
        self.lines[name] = dict(points=((x1, y1), (x2, y2)), style=style, pattern=pattern, arrow=arrow)

    def _to_back(self, name: str) -> None:
        self.z_order.remove(name)
        self.z_order.insert(1 if self.z_order[:1] == [BACKGROUND] and name != BACKGROUND else 0, name)

    def move(self, name: str, x: float, y: float) -> None:
        s = self._get(name)
        s.x, s.y = x, y

    def delete(self, name: str) -> None:
        self._get(name)
        doomed = [name] + [k for k, v in self.edges.items() if name in (v["source"], v["target"])]
        for n in doomed:
            del self.items[n]
            self.z_order.remove(n)
            for d in (self.edges, self.containers, self.runs, self.styles, self.edge_styles, self.boxes,
                      self.texts, self.lines, self.fills, self.container_styles, self.container_bounds):
                d.pop(n, None)

    def shapes(self) -> list[ShapeInfo]:
        return list(self.items.values())

    # page
    def set_page(self, width: float, height: float, background: str | None = None) -> None:
        self.page = dict(width=width, height=height, background=background)
        if BACKGROUND in self.items:
            self.delete(BACKGROUND)
        if background is not None:
            self._add(ShapeInfo(BACKGROUND, "", None, width / 2, height / 2, width, height))
            self.boxes[BACKGROUND] = ShapeStyle(fill=background, line=None)
            self._to_back(BACKGROUND)

    def present(self) -> None:
        self.presented += 1

    def _add(self, info: ShapeInfo) -> None:
        if info.name in self.items:
            raise KeyError(f"duplicate shape name {info.name!r}")
        self.items[info.name] = info
        self.z_order.append(info.name)

    def _get(self, name: str) -> ShapeInfo:
        if name not in self.items:
            raise KeyError(f"no shape named {name!r}")
        return self.items[name]
