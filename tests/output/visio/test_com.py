"""Real-Visio tests for VisioCom. Run with: uv run pytest -m visio"""

from __future__ import annotations

import faulthandler

import pytest

pythoncom = pytest.importorskip("pythoncom")

import pywintypes  # noqa: E402
import win32com.client  # noqa: E402

from visio_mcp.output.visio.backend import TextRun  # noqa: E402
from visio_mcp.output.visio.com import BACKGROUND, VisioCom  # noqa: E402
from visio_mcp.style import PROFESSIONAL, EdgeStyle, ShapeStyle, TextStyle  # noqa: E402

pytestmark = pytest.mark.visio


@pytest.fixture(scope="module")
def visio():
    pythoncom.CoInitialize()
    v = VisioCom(visible=False)
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
    """Nodes only: no connectors, containers or decorations (background, title, legend)."""
    return [s for s in v.shapes() if not (s.is_connector or s.is_container or s.name.startswith("__"))]


def shutdown(v):
    """Close a visible instance without leaving it running: nothing is unsaved after this."""
    faulthandler.disable()
    for d in v._app.Documents:
        d.Saved = True
    v.close()


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


# --- styling, rich text, containers, page --------------------------------------------------


def formula(v, name: str, cell: str) -> str:
    return v._find(name).CellsU(cell).FormulaU.replace(" ", "")


def result(v, name: str, cell: str) -> float:
    return v._find(name).CellsU(cell).ResultIU


def char_rows(v, name: str) -> list[dict]:
    """Character rows of a shape as {size (pt), color formula, style bits}."""
    s = v._find(name)
    rows = []
    for r in range(s.RowCount(3)):  # visSectionCharacter
        rows.append(dict(
            color=s.CellsSRC(3, r, 1).FormulaU.replace(" ", ""),
            style=int(s.CellsSRC(3, r, 2).ResultIU),
            size=round(s.CellsSRC(3, r, 7).Result("pt"), 2),
        ))
    return rows


def test_style_shape_sets_cells(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0, width=1.75, height=0.75)
    st = ShapeStyle(fill="#EFF6FF", line="#3B82F6", line_weight=1.5, line_pattern="dashed", rounding=0.08,
                    text=TextStyle("Segoe UI", 11, "#0F172A", bold=True))
    v.style_shape("a", st)
    assert formula(v, "a", "FillForegnd") == "RGB(239,246,255)"
    assert result(v, "a", "FillPattern") == 1
    assert formula(v, "a", "LineColor") == "RGB(59,130,246)"
    assert result(v, "a", "LinePattern") == 2
    assert round(v._find("a").CellsU("LineWeight").Result("pt"), 2) == 1.5
    assert round(result(v, "a", "Rounding"), 3) == 0.08
    assert result(v, "a", "ShdwPattern") == 0
    assert round(v._find("a").CellsU("Char.Size").Result("pt"), 2) == 11
    assert formula(v, "a", "Char.Color") == "RGB(15,23,42)"
    assert int(result(v, "a", "Char.Style")) & 1  # bold
    assert result(v, "a", "Para.HorzAlign") == 1  # centered


def test_style_shape_no_fill_no_line(v):
    v.drop_shape("a", "BASIC_U.VSSX", "Rectangle", 2.0, 3.0)
    v.style_shape("a", ShapeStyle(fill=None, line=None))
    assert result(v, "a", "FillPattern") == 0 and result(v, "a", "LinePattern") == 0


def test_icon_keeps_fill_and_puts_label_below(v):
    v.drop_shape("i", "BASFLO_U.VSSX", "Process", 2.0, 3.0, width=0.7, height=0.7)
    v.set_fill("i", "#FF0000")
    v.style_shape("i", PROFESSIONAL.node_style("compute"), keep_fill=True, label_below=True)
    v.set_text("i", "Web App")
    assert formula(v, "i", "FillForegnd") == "RGB(255,0,0)"  # untouched
    assert result(v, "i", "TxtPinY") < 0  # text block hangs under the shape
    assert result(v, "i", "TxtWidth") >= 1.7 - 1e-6
    assert result(v, "i", "VerticalAlign") == 0


def test_rich_text_runs(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0, width=2.0, height=1.0)
    bold = TextStyle("Segoe UI", 10, "#0F172A", bold=True)
    small = TextStyle("Segoe UI", 8, "#475569")
    v.set_rich_text("a", [TextRun("API", bold), TextRun("\n[FastAPI]", small)])
    assert v._find("a").Text == "API\n[FastAPI]"
    rows = char_rows(v, "a")
    assert dict(color="RGB(15,23,42)", style=1, size=10.0) in rows
    assert dict(color="RGB(71,85,105)", style=0, size=8.0) in rows
    v.style_shape("a", PROFESSIONAL.node_style("compute"))  # base style must not flatten the runs
    assert len({(r["size"], r["style"]) for r in char_rows(v, "a")}) == 2


def test_style_connector(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 1.5, 3.0)
    v.drop_shape("b", "BASFLO_U.VSSX", "Process", 5.0, 1.0)
    v.connect("a->b", "a", "b", label="calls")
    v.style_connector("a->b", EdgeStyle(color="#64748B", weight=1.25, label_bg="#FFFFFF"), color="#FF0000")
    assert formula(v, "a->b", "LineColor") == "RGB(255,0,0)"
    assert result(v, "a->b", "ShapeRouteStyle") == 1
    assert result(v, "a->b", "ConLineRouteExt") == 1
    assert round(result(v, "a->b", "Rounding"), 3) == 0.08
    assert formula(v, "a->b", "TextBkgnd") == "RGB(255,255,255)"
    assert round(v._find("a->b").CellsU("Char.Size").Result("pt"), 2) == 8.5
    assert by_name(v)["a->b"].text == "calls"


def test_container_with_style_and_bounds(v):
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 3.0)
    v.drop_shape("b", "BASFLO_U.VSSX", "Process", 4.5, 3.0)
    gs = PROFESSIONAL.group_style("network")
    v.add_container("inner", "Inner", ["a", "b"], gs, bounds=(3.25, 3.2, 4.0, 1.8))
    v.drop_shape("c", "BASFLO_U.VSSX", "Process", 7.5, 3.0)
    v.add_container("outer", "Outer", ["inner", "c"], gs, bounds=(4.75, 3.35, 7.5, 2.9))
    s = by_name(v)
    for name, (x, y, w, h) in (("inner", (3.25, 3.2, 4.0, 1.8)), ("outer", (4.75, 3.35, 7.5, 2.9))):
        c = s[name]
        assert c.is_container
        assert (round(c.x, 3), round(c.y, 3), round(c.width, 3), round(c.height, 3)) == (x, y, w, h)
    assert (round(s["a"].x, 3), round(s["a"].y, 3)) == (2.0, 3.0)  # members did not move
    assert s["inner"].text == "Inner"
    assert formula(v, "inner", "FillForegnd") == "RGB(240,253,244)"
    assert result(v, "inner", "Para.HorzAlign") == 0  # label on the left
    # z-order: outer behind inner behind the members
    order = [sh.NameU for sh in v._page().Shapes]  # Shapes iterate back to front
    assert order.index("outer") < order.index("inner") < order.index("a")


def test_boxes_texts_lines(v):
    v.add_box("__legend", 3.0, 2.0, 2.0, 1.0, PROFESSIONAL.legend)
    v.add_text("__title", 3.0, 4.0, 4.0, 0.6,
               [TextRun("Title", PROFESSIONAL.title), TextRun("\nSub", PROFESSIONAL.subtitle)], align="left")
    v.add_line("__l1", 1.0, 1.0, 2.0, 1.0, PROFESSIONAL.edge, pattern="dashed", arrow="end")
    s = by_name(v)
    assert (round(s["__legend"].width, 3), round(s["__legend"].height, 3)) == (2.0, 1.0)
    assert s["__title"].text == "Title\nSub"
    assert result(v, "__title", "LinePattern") == 0 and result(v, "__title", "FillPattern") == 0
    assert result(v, "__title", "Para.HorzAlign") == 0
    assert s["__l1"].is_connector and result(v, "__l1", "LinePattern") == 2
    assert result(v, "__l1", "EndArrow") != 0
    with pytest.raises(KeyError):
        v.add_box("__legend", 0, 0, 1, 1, PROFESSIONAL.legend)


def test_page_background_covers_page_when_resized(v):
    v.set_page(11.0, 8.5, background="#0B1F3A")
    sheet = v._page().PageSheet
    assert (sheet.CellsU("PageWidth").ResultIU, sheet.CellsU("PageHeight").ResultIU) == (11.0, 8.5)
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 2.0)
    v.drop_shape("b", "BASFLO_U.VSSX", "Process", 6.0, 3.0)
    v.connect("a->b", "a", "b")
    v.add_container("g", "G", ["a"])
    v.set_page(7.0, 4.0, background="#F8FAFC")  # resizes the existing background
    bg = by_name(v)[BACKGROUND]
    assert (round(bg.x, 3), round(bg.y, 3), round(bg.width, 3), round(bg.height, 3)) == (3.5, 2.0, 7.0, 4.0)
    assert formula(v, BACKGROUND, "FillForegnd") == "RGB(248,250,252)"
    assert v._page().Shapes(1).NameU == BACKGROUND  # still the very back, behind the container
    v.set_page(7.0, 4.0, background=None)
    assert BACKGROUND not in by_name(v)
    v.present()  # no-op headless


# --- visible, live and attach -----------------------------------------------------------------


def _draw_small(v):
    v.new_document("live")
    v.set_page(8.0, 5.0, background="#F8FAFC")
    v.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 2.5)
    v.drop_shape("b", "BASFLO_U.VSSX", "Process", 5.0, 2.5)
    v.style_shape("a", PROFESSIONAL.node_style("flow"))
    v.connect("a->b", "a", "b", label="next")
    v.style_connector("a->b", PROFESSIONAL.edge)
    v.add_container("g", "Group", ["a", "b"], PROFESSIONAL.group_style("generic"))
    v.present()
    return by_name(v)


def test_live_visible_mode_draws_and_presents(tmp_path):
    v = VisioCom(visible=True, live_delay=0.02)
    try:
        s = _draw_small(v)
        assert {"a", "b", "a->b", "g", BACKGROUND} <= set(s)
        saved = v.save(str(tmp_path / "live.vsdx"))
        v.new_document("second")  # the saved, untouched first drawing may close; no prompt either way
        v.drop_shape("x", "BASFLO_U.VSSX", "Process", 2.0, 2.0)
        assert saved.endswith("live.vsdx")
    finally:
        shutdown(v)


def test_attach_falls_back_to_starting_visio(monkeypatch):
    def nothing_running(prog_id, *args):
        raise pywintypes.com_error(-2147221021, "Operation unavailable", None, None)  # MK_E_UNAVAILABLE

    monkeypatch.setattr(win32com.client, "GetActiveObject", nothing_running)
    v = VisioCom(attach=True)
    try:
        assert v._owns_app
        assert "a" in _draw_small(v)
    finally:
        shutdown(v)


def test_attach_never_quits_the_users_visio():
    owner = VisioCom(visible=True)  # stands in for the user's own Visio window
    try:
        guest = VisioCom(attach=True)
        assert not guest._owns_app  # found a running Visio
        guest.new_document("guest drawing")
        guest.drop_shape("a", "BASFLO_U.VSSX", "Process", 2.0, 2.0)
        guest.close()
        owner.new_document("still alive")  # the app guest attached to is still running
        owner.drop_shape("b", "BASFLO_U.VSSX", "Process", 2.0, 2.0)
        assert "b" in by_name(owner)
    finally:
        shutdown(owner)
