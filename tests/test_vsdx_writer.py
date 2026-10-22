"""Native .vsdx writer: package structure, shapes, glue, text, and a LibreOffice render."""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from visio_mcp.layout import Rect
from visio_mcp.plan import DiagramPlan, build_plan
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GEOMETRY_MIN, ICON_SIZE
from visio_mcp.vsdx_writer import write_vsdx

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
V = "{http://schemas.microsoft.com/office/visio/2012/main}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

REQUIRED_PARTS = {
    "[Content_Types].xml": None,
    "_rels/.rels": None,
    "docProps/app.xml": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    "docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
    "visio/document.xml": "application/vnd.ms-visio.drawing.main+xml",
    "visio/_rels/document.xml.rels": None,
    "visio/pages/pages.xml": "application/vnd.ms-visio.pages+xml",
    "visio/pages/_rels/pages.xml.rels": None,
    "visio/pages/page1.xml": "application/vnd.ms-visio.page+xml",
    "visio/windows.xml": "application/vnd.ms-visio.windows+xml",
}


def _plan(name: str = "web-architecture", **overrides) -> DiagramPlan:
    data = json.loads((EXAMPLES / f"{name}.json").read_text())
    data.update(overrides)
    return build_plan(DiagramSpec.model_validate(data))


def _xml(path: Path, part: str) -> ET.Element:
    with zipfile.ZipFile(path) as z:
        return ET.fromstring(z.read(part))


def _all_shapes(page: ET.Element) -> list[ET.Element]:
    return list(page.iter(f"{V}Shape"))


def _cells(shape: ET.Element) -> dict[str, str]:
    return {c.get("N"): c.get("V") for c in shape.findall(f"{V}Cell")}


@pytest.fixture
def written(tmp_path: Path) -> tuple[DiagramPlan, Path]:
    plan = _plan()
    return plan, write_vsdx(plan, tmp_path / "out" / "diagram.vsdx")


def test_returns_absolute_path_and_zip(written):
    _, path = written
    assert path.is_absolute() and path.exists()
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None


def test_required_parts_and_content_types(written):
    _, path = written
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    assert set(REQUIRED_PARTS) <= names
    types = _xml(path, "[Content_Types].xml")
    defaults = {d.get("Extension"): d.get("ContentType") for d in types.findall(f"{CT}Default")}
    overrides = {o.get("PartName"): o.get("ContentType") for o in types.findall(f"{CT}Override")}
    assert defaults["rels"] == "application/vnd.openxmlformats-package.relationships+xml"
    assert defaults["xml"] == "application/xml"
    for part, ct in REQUIRED_PARTS.items():
        if ct:
            assert overrides["/" + part] == ct


def test_every_part_is_well_formed_xml(written):
    _, path = written
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            ET.fromstring(z.read(name))  # raises on malformed XML


def test_relationships_resolve(written):
    _, path = written
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    expect = {
        "_rels/.rels": ("", {"http://schemas.microsoft.com/visio/2010/relationships/document"}),
        "visio/_rels/document.xml.rels": ("visio/", {
            "http://schemas.microsoft.com/visio/2010/relationships/pages",
            "http://schemas.microsoft.com/visio/2010/relationships/windows",
        }),
        "visio/pages/_rels/pages.xml.rels": ("visio/pages/", {
            "http://schemas.microsoft.com/visio/2010/relationships/page",
        }),
    }
    for rels_part, (base, needed) in expect.items():
        rels = _xml(path, rels_part).findall(f"{PR}Relationship")
        ids = [r.get("Id") for r in rels]
        assert len(ids) == len(set(ids))
        assert needed <= {r.get("Type") for r in rels}
        for r in rels:
            assert base + r.get("Target") in names
    # the page entry points at its part through the r:id
    page = _xml(path, "visio/pages/pages.xml").find(f"{V}Page")
    rel = page.find(f"{V}Rel")
    assert rel.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") == "rId1"


def test_page_size_matches_plan(written):
    plan, path = written
    sheet = _xml(path, "visio/pages/pages.xml").find(f"{V}Page/{V}PageSheet")
    cells = _cells(sheet)
    assert float(cells["PageWidth"]) == pytest.approx(plan.width)
    assert float(cells["PageHeight"]) == pytest.approx(plan.height)


def test_core_title(written):
    plan, path = written
    core = _xml(path, "docProps/core.xml")
    assert core.find("{http://purl.org/dc/elements/1.1/}title").text == plan.spec.title


def test_one_named_shape_per_node_group_and_edge(written):
    plan, path = written
    shapes = _all_shapes(_xml(path, "visio/pages/page1.xml"))
    ids = [s.get("ID") for s in shapes]
    assert len(ids) == len(set(ids)), "shape IDs must be unique on the page"
    names = [s.get("NameU") for s in shapes]
    assert len(names) == len(set(names))
    for nid in [n.id for n in plan.nodes] + [g.id for g in plan.groups] + [e.name for e in plan.edges]:
        assert names.count(nid) == 1, nid
    by_name = {s.get("NameU"): s for s in shapes}
    for s in shapes:
        assert s.get("Name") == s.get("NameU")
        assert s.get("Type") in ("Shape", "Group")
    for g in plan.groups:
        user = by_name[g.id].find(f"{V}Section[@N='User']")
        row = user.find(f"{V}Row[@N='msvStructureType']")
        assert row.find(f"{V}Cell[@N='Value']").get("V") == "Container"
    assert "__background" in by_name and "__title" in by_name
    if plan.legend:
        assert "__legend" in by_name
        assert sum(1 for n in names if n.startswith("__legend_") and n.endswith("_sample")) == len(plan.legend_entries)


def test_background_is_first_and_locked(written):
    plan, path = written
    page = _xml(path, "visio/pages/page1.xml")
    first = page.find(f"{V}Shapes/{V}Shape")
    assert first.get("NameU") == "__background"
    c = _cells(first)
    assert c["FillForegnd"] == plan.theme.background.upper()
    assert c["LockSelect"] == "1" and c["LockMoveX"] == "1"
    assert float(c["Width"]) == pytest.approx(plan.width)


def test_connectors_are_glued_1d_shapes(written):
    plan, path = written
    page = _xml(path, "visio/pages/page1.xml")
    shapes = {s.get("NameU"): s for s in _all_shapes(page)}
    ids = {s.get("ID"): s.get("NameU") for s in shapes.values()}
    connects = page.findall(f"{V}Connects/{V}Connect")
    for c in connects:
        assert c.get("FromSheet") in ids and c.get("ToSheet") in ids
        assert c.get("FromCell") in ("BeginX", "EndX")
        assert c.get("ToCell") == "PinX"
    for e in plan.edges:
        conn = shapes[e.name]
        cells = _cells(conn)
        for k in ("BeginX", "BeginY", "EndX", "EndY"):
            assert k in cells
        assert cells["ObjType"] == "2"
        assert cells["EndArrow"] == ("0" if e.arrow == "none" else "13")
        assert cells["BeginArrow"] == ("13" if e.arrow == "both" else "0")
        assert cells["LineColor"] == e.color.upper()
        assert cells["LinePattern"] == {"solid": "1", "dashed": "2", "dotted": "3"}[e.pattern]
        mine = {c.get("FromCell"): ids[c.get("ToSheet")] for c in connects if c.get("FromSheet") == conn.get("ID")}
        assert mine == {"BeginX": e.source, "EndX": e.target}
        # geometry follows the planned route, in coordinates local to the begin point
        rows = conn.find(f"{V}Section[@N='Geometry']").findall(f"{V}Row")
        assert len(rows) == max(2, len(e.points))
        bx, by = e.points[0]
        last = rows[-1]
        ex, ey = e.points[-1]
        assert float(last.find(f"{V}Cell[@N='X']").get("V")) == pytest.approx(ex - bx, abs=1e-6)
        assert float(last.find(f"{V}Cell[@N='Y']").get("V")) == pytest.approx(ey - by, abs=1e-6)
        if e.label:
            assert "".join(conn.find(f"{V}Text").itertext()) == e.label


def test_node_text_runs_and_styles(tmp_path: Path):
    plan = _plan(nodes=[
        {"id": "api", "label": "Orders API", "kind": "service", "technology": "FastAPI",
         "description": "Takes orders"},
        {"id": "db", "label": "Orders DB", "kind": "database"},
    ], edges=[{"source": "api", "target": "db", "label": "SQL"}], groups=[])
    path = write_vsdx(plan, tmp_path / "t.vsdx")
    shapes = {s.get("NameU"): s for s in _all_shapes(_xml(path, "visio/pages/page1.xml"))}
    for n in plan.nodes:
        s = shapes[n.id]
        text = s.find(f"{V}Text")
        assert "".join(text.itertext()) == "".join(r.text for r in n.runs)
        chars = s.find(f"{V}Section[@N='Character']").findall(f"{V}Row")
        assert len(text.findall(f"{V}cp")) == len(n.runs)
        for r in n.runs:
            row = chars[[int(cp.get("IX")) for cp in text.findall(f"{V}cp")][n.runs.index(r)]]
            cells = _cells(row)
            assert cells["Font"] == r.style.font
            assert cells["Color"] == r.style.color.upper()
            assert float(cells["Size"]) == pytest.approx(r.style.size / 72)
            assert int(cells["Style"]) & 1 == int(r.style.bold)
        c = _cells(s)
        assert c["FillForegnd"] == n.style.fill.upper()
        assert float(c["Width"]) == pytest.approx(n.shape.w)
        assert float(c["PinX"]) == pytest.approx(n.shape.x)


def test_styles_and_fonts_referenced_exist(written):
    _, path = written
    doc = _xml(path, "visio/document.xml")
    style_ids = {s.get("ID") for s in doc.iter(f"{V}StyleSheet")}
    assert "0" in style_ids
    assert any(s.get("NameU") == "No Style" for s in doc.iter(f"{V}StyleSheet"))
    faces = {f.get("NameU") for f in doc.iter(f"{V}FaceName")}
    page = _xml(path, "visio/pages/page1.xml")
    for s in _all_shapes(page):
        for attr in ("LineStyle", "FillStyle", "TextStyle"):
            assert s.get(attr) in style_ids
        for row in s.findall(f"{V}Section[@N='Character']/{V}Row"):
            assert _cells(row)["Font"] in faces


@pytest.mark.parametrize("name", sorted(p.stem for p in EXAMPLES.glob("*.json")))
def test_all_examples_write(tmp_path: Path, name: str):
    path = write_vsdx(_plan(name), tmp_path / f"{name}.vsdx")
    with zipfile.ZipFile(path) as z:
        for part in z.namelist():
            ET.fromstring(z.read(part))


def _gallery_plan() -> DiagramPlan:
    """Every geometry once (the catalog may not use all of them yet)."""
    geoms = list(GEOMETRY_MIN)
    plan = _plan(nodes=[{"id": g, "label": g.title(), "kind": "service"} for g in geoms],
                 edges=[{"source": a, "target": b} for a, b in zip(geoms, geoms[1:])], groups=[], legend=False)
    for n in plan.nodes:
        n.geometry = n.id
        if n.id in ("icon", "person"):
            n.icon = True
            n.shape = Rect(n.rect.x, n.rect.top - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE)
    return plan


def test_every_geometry_draws(tmp_path: Path):
    plan = _gallery_plan()
    path = write_vsdx(plan, tmp_path / "gallery.vsdx")
    shapes = {s.get("NameU"): s for s in _all_shapes(_xml(path, "visio/pages/page1.xml"))}
    for n in plan.nodes:
        s = shapes[n.id]
        sections = s.findall(f"{V}Section[@N='Geometry']")
        assert sections, n.id
        for sec in sections:
            rows = sec.findall(f"{V}Row")
            assert rows and rows[0].get("T") in ("MoveTo", "Ellipse"), n.id
    # icon tiles carry their glyph in a child shape and the label below the tile
    icon = shapes["icon"]
    assert icon.get("Type") == "Group"
    assert icon.find(f"{V}Shapes/{V}Shape") is not None
    assert float(_cells(icon)["TxtPinY"]) < 0
    assert float(_cells(shapes["person"])["TxtPinY"]) < 0


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice (soffice) not installed")
def test_libreoffice_renders_png(tmp_path: Path):
    path = write_vsdx(_plan(), tmp_path / "render.vsdx")
    out = tmp_path / "png"
    subprocess.run(["soffice", "--headless", "--convert-to", "png", "--outdir", str(out), str(path)],
                   check=True, capture_output=True, timeout=180)
    png = out / "render.png"
    assert png.exists() and png.stat().st_size > 5000
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
