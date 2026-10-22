"""Real-Visio tests for VisioCom. Run with: uv run pytest -m visio"""

from __future__ import annotations

import faulthandler

import pytest

pythoncom = pytest.importorskip("pythoncom")

from visio_mcp.visio_com import VisioCom  # noqa: E402

pytestmark = pytest.mark.visio


@pytest.fixture(scope="module")
def visio():
    pythoncom.CoInitialize()
    v = VisioCom()
    try:
        yield v
    finally:
        faulthandler.disable()  # Quit() raises a benign RPC_E_DISCONNECTED that it would print
        v.close()


@pytest.fixture
def v(visio):
    visio.new_document("test")
    return visio


def by_name(v) -> dict:
    return {s.name: s for s in v.shapes()}


def boxes(v):
    return [s for s in v.shapes() if not (s.is_connector or s.is_container)]


def overlaps(v) -> list[tuple[str, str]]:
    bs, out = boxes(v), []
    for i, a in enumerate(bs):
        for b in bs[i + 1 :]:
            if abs(a.x - b.x) < (a.width + b.width) / 2 - 1e-6 and abs(a.y - b.y) < (a.height + b.height) / 2 - 1e-6:
                out.append((a.name, b.name))
    return out


def test_list_stencils_and_masters(v):
    stencils = v.list_stencils()
    assert "BASFLO_U.VSSX" in stencils and "BASIC_U.VSSX" in stencils
    assert all(s.upper().endswith("_U.VSSX") for s in stencils)
    assert "Process" in v.list_masters("BASFLO_U.VSSX")
    assert v.list_masters("NOPE_U.VSSX") == []


def test_has_master(v):
    assert v.has_master("BASFLO_U.VSSX", "Decision")
    assert v.has_master("BASIC_U.VSSX", "Rectangle")
    assert not v.has_master("BASFLO_U.VSSX", "Nonsense Shape")
    assert not v.has_master("NOPE_U.VSSX", "Process")


def test_drop_text_fill_and_shapes(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0)
    v.drop_shape("b", "BASIC_U.VSSX", "Rectangle", 5.0, 3.0, width=2.0, height=1.0)
    v.set_text("a", "Hello")
    v.set_fill("b", "#FF8000")
    s = by_name(v)
    assert s["a"].text == "Hello" and s["a"].master == "Process"
    assert (round(s["a"].x, 3), round(s["a"].y, 3)) == (2.0, 3.0)
    assert s["b"].master == "Rectangle"
    assert (round(s["b"].width, 3), round(s["b"].height, 3)) == (2.0, 1.0)
    assert not s["a"].is_connector and not s["a"].is_container
    assert v._find("b").CellsU("FillForegnd").FormulaU.replace(" ", "") == "RGB(255,128,0)"


def test_org_chart_master_drop_does_not_hang(v):
    # ORGCH masters run an add-on from EventDrop; with events enabled this blocks headless Visio.
    v.drop_shape("ceo", "ORGCH_U.VSSX", "Executive", 2.0, 2.0)
    v.set_text("ceo", "CEO")
    assert by_name(v)["ceo"].master == "Executive"


def test_missing_names_raise_keyerror(v):
    with pytest.raises(KeyError):
        v.set_text("ghost", "x")
    with pytest.raises(KeyError):
        v.drop_shape("z", "BASFLO_U.VSSX", "Nonsense Shape", 1, 1)
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 1, 1)
    with pytest.raises(KeyError):
        v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2, 2)


def test_connect_styles(v):
    for i, n in enumerate("abc"):
        v.drop_shape(n, "BASFLO_U.VSSX", "Process", 1.5 + 2.5 * i, 3.0)
    v.connect("a->b", "a", "b", label="yes", pattern="dashed", arrow="both")
    v.connect("b->c", "b", "c", pattern="dotted", arrow="none")
    v.connect("a->c", "a", "c")
    s = by_name(v)
    assert s["a->b"].is_connector and s["a->b"].text == "yes"
    assert s["a->b"].master == "Dynamic connector"
    ab, bc, ac = (v._find(n) for n in ("a->b", "b->c", "a->c"))
    assert ab.CellsU("LinePattern").ResultIU == 2 and bc.CellsU("LinePattern").ResultIU == 3
    assert ac.CellsU("LinePattern").ResultIU == 1
    assert ab.CellsU("BeginArrow").ResultIU != 0 and ab.CellsU("EndArrow").ResultIU != 0
    assert bc.CellsU("BeginArrow").ResultIU == 0 and bc.CellsU("EndArrow").ResultIU == 0
    assert ac.CellsU("BeginArrow").ResultIU == 0 and ac.CellsU("EndArrow").ResultIU != 0
    with pytest.raises(KeyError):
        v.connect("a->zz", "a", "zz")


def test_container_around_two_shapes(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0)
    v.drop_shape("b", "BASFLO_U.VSSX", "Process", 4.5, 3.0)
    v.add_container("grp", "Group label", ["a", "b"])
    s = by_name(v)
    c = s["grp"]
    assert c.is_container and c.text == "Group label"
    for m in ("a", "b"):
        assert c.x - c.width / 2 <= s[m].x - s[m].width / 2 + 1e-6
        assert c.x + c.width / 2 >= s[m].x + s[m].width / 2 - 1e-6
        assert c.y - c.height / 2 <= s[m].y - s[m].height / 2 + 1e-6
        assert c.y + c.height / 2 >= s[m].y + s[m].height / 2 - 1e-6
    assert not s["a"].is_container


def test_move_and_delete_cascades(v):
    for i, n in enumerate("abc"):
        v.drop_shape(n, "BASFLO_U.VSSX", "Process", 1.5 + 2.5 * i, 3.0)
    v.connect("a->b", "a", "b")
    v.connect("b->c", "b", "c")
    v.move("c", 9.0, 6.0)
    c = by_name(v)["c"]
    assert (round(c.x, 3), round(c.y, 3)) == (9.0, 6.0)
    v.delete("b")
    assert set(by_name(v)) == {"a", "c"}
    with pytest.raises(KeyError):
        v.delete("b")


@pytest.mark.parametrize("preset", ["flowchart-tb", "tree-tb"])
def test_layout_has_no_overlaps(v, tmp_path, preset):
    edges = [("root", "l"), ("root", "r"), ("l", "ll"), ("l", "lr"), ("r", "rl"), ("r", "rr")]
    ids = ["root", "l", "r", "ll", "lr", "rl", "rr"]
    for n in ids:  # start deliberately stacked
        v.drop_shape(n, "BASFLO_U.VSSX", "Process", 2.0, 2.0)
        v.set_text(n, n)
    for a, b in edges:
        v.connect(f"{a}->{b}", a, b)
    v.layout(preset)
    assert overlaps(v) == []
    s = by_name(v)
    assert s["root"].y > s["ll"].y  # root on top
    png = v.export(str(tmp_path / f"{preset}.png"))
    assert (tmp_path / f"{preset}.png").stat().st_size > 1000 and png.endswith(".png")


@pytest.mark.parametrize("preset", ["flowchart-lr", "tree-lr", "radial", "circular", "compact", "none"])
def test_other_layout_presets_run(v, preset):
    for i in range(5):
        v.drop_shape(f"n{i}", "BASFLO_U.VSSX", "Process", 2.0, 2.0)
    for i in range(1, 5):
        v.connect(f"n0->n{i}", "n0", f"n{i}")
    v.layout(preset)
    if preset != "none":
        assert overlaps(v) == []
    with pytest.raises(ValueError):
        v.layout("bogus")


def test_save_and_export(v, tmp_path):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0)
    v.set_text("a", "Hi")
    vsdx = tmp_path / "sub" / "d.vsdx"
    assert v.save(str(vsdx)) == str(vsdx)
    assert v.save(str(vsdx)) == str(vsdx)  # re-save same document
    other = tmp_path / "copy.vsdx"
    other.write_bytes(b"old")
    v.save(str(other))  # overwrite existing file
    assert other.stat().st_size > 100
    for ext in ("png", "svg", "pdf", "jpg"):
        out = v.export(str(tmp_path / "out" / f"d.{ext}"))
        assert out.endswith(f".{ext}")
        assert (tmp_path / "out" / f"d.{ext}").stat().st_size > 0
    with pytest.raises(ValueError):
        v.export(str(tmp_path / "d.xyz"))
    v.open_document(str(vsdx))
    assert by_name(v)["a"].text == "Hi"
