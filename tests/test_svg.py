import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from visio_mcp import svg as svgmod
from visio_mcp.plan import build_plan
from visio_mcp.spec import DiagramSpec

EXAMPLES = Path(__file__).parent.parent / "examples"
NS = {"s": "http://www.w3.org/2000/svg"}


def _plan(name="web-architecture", **over):
    d = json.loads((EXAMPLES / f"{name}.json").read_text())
    d.update(over)
    return build_plan(DiagramSpec.model_validate(d))


def _root(plan):
    return ET.fromstring(svgmod.render_svg(plan))


@pytest.mark.parametrize("f", sorted(p.stem for p in EXAMPLES.glob("*.json")))
def test_examples_valid_xml_and_ids(f):
    plan = _plan(f)
    root = _root(plan)
    nodes = {g.get("data-id") for g in root.iterfind(".//s:g[@class='node']", NS)}
    edges = [g.get("data-id") for g in root.iterfind(".//s:g[@class='edge']", NS)]
    groups = {g.get("data-id") for g in root.iterfind(".//s:g[@class='group']", NS)}
    assert nodes == {n.id for n in plan.nodes}
    assert edges == [e.name for e in plan.edges]
    assert groups == {g.id for g in plan.groups}


@pytest.mark.parametrize("theme", ["azure", "aws", "c4", "blueprint", "dark", "monochrome", "gcp"])
def test_themes_render(theme):
    root = _root(_plan(theme=theme))
    assert root.get("data-theme") == theme


def test_text_present_and_escaped():
    d = json.loads((EXAMPLES / "web-architecture.json").read_text())
    d["nodes"][0]["label"] = 'R&D <Core> "x"'
    plan = build_plan(DiagramSpec.model_validate(d))
    text = svgmod.render_svg(plan)
    assert "&amp;" in text and "&lt;" in text and "<Core>" not in text
    root = ET.fromstring(text)
    joined = "".join(root.itertext())
    assert "R&D" in joined and "<Core>" in joined


def test_y_flip():
    plan = _plan()
    ns = sorted(plan.nodes, key=lambda n: n.shape.y)
    a, b = ns[0], ns[-1]
    assert b.shape.y > a.shape.y
    root = _root(plan)

    def top(nid):
        g = root.find(f".//s:g[@data-id='{nid}']", NS)
        ys = []
        for el in g.iter():
            for k in ("y", "cy"):
                if el.get(k):
                    ys.append(float(el.get(k)))
        return sum(ys) / len(ys)

    assert top(b.id) < top(a.id)  # larger plan y -> smaller svg y (higher up)


def test_viewbox_matches_page():
    plan = _plan()
    root = _root(plan)
    vb = [float(v) for v in root.get("viewBox").split()]
    assert vb[2] == pytest.approx(plan.width * 96, abs=0.01)
    assert vb[3] == pytest.approx(plan.height * 96, abs=0.01)


def test_write_html(tmp_path):
    plan = _plan()
    out = svgmod.write_html(plan, tmp_path / "v.html")
    t = out.read_text()
    assert "<svg" in t and "data-id=" in t and "Download" in t
    assert "http://" not in t.replace("http://www.w3.org/2000/svg", "")


def test_svg_to_png_without_rasterizer(tmp_path, monkeypatch):
    p = tmp_path / "a.svg"
    p.write_text(svgmod.render_svg(_plan()))
    monkeypatch.setattr(svgmod, "_png_playwright", lambda *a, **k: False)
    monkeypatch.setattr(svgmod, "_png_cairosvg", lambda *a, **k: False)
    assert svgmod.svg_to_png(p, tmp_path / "a.png") is None


def test_svg_to_png_swallows_errors(tmp_path, monkeypatch):
    p = tmp_path / "a.svg"
    p.write_text(svgmod.render_svg(_plan()))

    def boom(*a, **k):
        raise RuntimeError("no browser")

    monkeypatch.setattr(svgmod, "_png_playwright", boom)
    monkeypatch.setattr(svgmod, "_png_cairosvg", boom)
    assert svgmod.svg_to_png(p, tmp_path / "a.png") is None
