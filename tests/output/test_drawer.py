"""Drawer: native rendering, patching, exporting and saving around locked files; Visio via FakeVisio."""

import zipfile
from pathlib import Path

import pytest
from fake_visio import FakeVisio

from visio_mcp.output import native
from visio_mcp.output.drawer import Drawer
from visio_mcp.spec import AddNode, DiagramSpec, Edge, Node, UpdateNode

SPEC = DiagramSpec(
    title="Hello World",
    nodes=[Node(id="a", kind="process"), Node(id="b", kind="decision")],
    edges=[Edge(source="a", target="b")],
)


@pytest.fixture
def no_png(monkeypatch):
    """No rasterizer or LibreOffice: png/pdf previews cannot be made."""
    monkeypatch.setattr(native.svg, "svg_to_png", lambda *a, **k: None)
    monkeypatch.setattr(native, "soffice_convert", lambda *a, **k: None)


def test_native_render_writes_vsdx_and_previews(tmp_path):
    out = Drawer(target="native").render(SPEC, tmp_path / "hello.vsdx", ["svg", "html"])
    assert out.target == "native" and out.vsdx == (tmp_path / "hello.vsdx").resolve()
    assert zipfile.is_zipfile(out.vsdx)
    assert set(out.previews) == {"svg", "html"}
    assert out.result.files == [str(out.vsdx), str(out.previews["svg"]), str(out.previews["html"])]
    assert out.result.shapes == 2 and out.result.connectors == 1 and out.plan is not None


def test_native_render_skips_formats_it_cannot_make(tmp_path, no_png):
    out = Drawer(target="native").render(SPEC, tmp_path / "hello.vsdx", ["png", "html"])
    assert set(out.previews) == {"html"} and out.png is None
    assert not (tmp_path / "hello.svg").exists()  # svg was only the source of the png
    assert any("no renderer for png" in w for w in out.result.warnings)


def test_native_patch_rerenders_from_the_spec(tmp_path):
    d = Drawer(target="native")
    d.render(SPEC, tmp_path / "hello.vsdx", ["svg"])
    out = d.patch([UpdateNode(id="a", label="Start"), AddNode(node=Node(id="c", kind="database"))])
    assert out.result.shapes == 3 and set(out.previews) == {"svg"}
    assert [n.label for n in d.spec.nodes][0] == "Start"
    assert "Start" in out.previews["svg"].read_text()


def test_patch_and_export_need_an_open_diagram():
    d = Drawer(target="native")
    with pytest.raises(ValueError, match="no diagram open"):
        d.patch([UpdateNode(id="a", label="x")])
    with pytest.raises(ValueError, match="no diagram open"):
        d.export("svg")
    with pytest.raises(ValueError, match="no diagram open"):
        d.inspect()


def test_native_export(tmp_path, no_png):
    d = Drawer(target="native")
    d.render(SPEC, tmp_path / "hello.vsdx", [])
    assert d.export("svg") == (tmp_path / "hello.svg").resolve()
    assert d.export("html", tmp_path / "other" / "view.png") == tmp_path / "other" / "view.html"
    with pytest.raises(RuntimeError, match="could not export pdf"):
        d.export("pdf")


def test_native_inspect_reports_the_plan(tmp_path):
    d = Drawer(target="native")
    d.render(SPEC, tmp_path / "hello.vsdx", [])
    info = d.inspect()
    assert [s["id"] for s in info["shapes"]] == ["a", "b"]
    assert info["connectors"][0]["source"] == "a" and info["overlaps"] == []


def test_native_locked_file_saves_under_a_free_name(tmp_path, monkeypatch):
    real = native.write_vsdx

    def write(plan, path):
        if Path(path).name == "hello.vsdx":
            raise PermissionError("in use")
        return real(plan, path)

    monkeypatch.setattr(native, "write_vsdx", write)
    d = Drawer(target="native")
    out = d.render(SPEC, tmp_path / "hello.vsdx", ["svg"])
    assert out.vsdx.name == "hello-2.vsdx" and out.previews["svg"].name == "hello-2.svg"
    assert any("open in another program; saved as hello-2.vsdx" in w for w in out.result.warnings)
    assert d.vsdx == out.vsdx  # later patches and exports go to the file that was written


def test_visio_target_needs_visio():
    with pytest.raises(RuntimeError, match="not installed"):
        Drawer(target="visio")
    assert Drawer(target="auto").target == "native"  # no Visio on this machine


def test_visio_render_saves_and_exports_through_the_backend(tmp_path):
    fake = FakeVisio()
    d = Drawer(backend=fake)
    out = d.render(SPEC, tmp_path / "hello.vsdx", ["png", "html"])
    assert out.target == "visio" and out.plan is not None
    assert set(out.previews) == {"png"}  # html is native-only
    assert fake.files == [str((tmp_path / "hello.vsdx").resolve()), str((tmp_path / "hello.png").resolve())]


def test_visio_locked_file_saves_under_a_free_name(tmp_path, monkeypatch):
    real = FakeVisio.save

    def save(self, path):
        if path.endswith("hello.vsdx"):
            raise PermissionError("in use")
        return real(self, path)

    monkeypatch.setattr(FakeVisio, "save", save)
    d = Drawer(backend=FakeVisio())
    out = d.render(SPEC, tmp_path / "hello.vsdx", [])
    assert out.vsdx.name == "hello-2.vsdx" and d.vsdx == out.vsdx
    assert any("saved as hello-2.vsdx" in w for w in out.result.warnings)


def test_visio_open_patches_shapes_in_place(tmp_path):
    drawing = tmp_path / "theirs.vsdx"
    drawing.write_bytes(b"x")
    d = Drawer(backend=FakeVisio())
    info = d.open(drawing)
    assert info["shapes"] == [] and d.spec is None
    out = d.patch([AddNode(node=Node(id="n", kind="process", label="New"))], formats=[])
    assert out.result.shapes == 1 and out.vsdx == drawing.resolve()
    assert d.export("pdf") == drawing.with_suffix(".pdf").resolve()


def test_open_rejects_other_files_and_native_target(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    with pytest.raises(ValueError, match=".vsdx"):
        Drawer(backend=FakeVisio()).open(notes)
    drawing = tmp_path / "d.vsdx"
    drawing.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="needs Microsoft Visio"):
        Drawer(target="native").open(drawing)


def test_close_releases_the_backend():
    d = Drawer(backend=FakeVisio())
    d.close()
    assert d._backend is None
