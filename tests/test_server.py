"""Tools called through the MCP layer, the way a client sees them (fake Visio backend)."""

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from fake_visio import FakeVisio
from visio_mcp import server
from visio_mcp.engine import Drawer

SPEC = {
    "title": "Hello World",
    "nodes": [{"id": "a", "kind": "process"}, {"id": "b", "kind": "decision"}],
    "edges": [{"source": "a", "target": "b"}],
}


@pytest.fixture(autouse=True)
def fake_server(monkeypatch, tmp_path):
    monkeypatch.setenv("VISIO_MCP_OUT", str(tmp_path))
    monkeypatch.setattr(server, "_drawer", Drawer(backend=FakeVisio()))
    return tmp_path


def call(name, args):
    return asyncio.run(server.mcp.call_tool(name, args))


def error(name, args) -> str:
    """The message a client sees for a failing call (MCP sends ToolError text, hides others)."""
    with pytest.raises(ToolError) as exc:
        call(name, args)
    return str(exc.value)


def backend() -> FakeVisio:
    return server._drawer._backend  # type: ignore[union-attr,return-value]


def test_render_returns_summary_and_preview_image(fake_server):
    res = call("render_diagram", {"spec": SPEC})
    assert not res.is_error, res.content
    assert [c.type for c in res.content] == ["text", "image"]
    summary = json.loads(res.content[0].text)
    assert summary["shapes"] == 2 and summary["connectors"] == 1
    assert summary["files"][0] == str(fake_server / "hello-world.vsdx")
    assert "suggestions" in summary


def test_invalid_spec_is_a_readable_error():
    assert "unknown nodes" in error("render_diagram", {"spec": {**SPEC, "edges": [{"source": "a", "target": "zz"}]}})


def test_patch_before_render_is_an_error():
    assert "no diagram open" in error("patch_diagram", {"ops": [{"op": "relayout", "layout": "radial"}]})


def test_patch_rerenders_from_the_spec(fake_server):
    call("render_diagram", {"spec": SPEC, "preview": False})
    res = call("patch_diagram", {"ops": [
        {"op": "update_node", "id": "a", "label": "go now"},
        {"op": "add_node", "node": {"id": "c", "kind": "database"}},
        {"op": "add_edge", "edge": {"source": "b", "target": "c", "label": "yes"}},
        {"op": "update_diagram", "theme": "dark"},
    ], "preview": False})
    assert not res.is_error, res.content
    assert [c.type for c in res.content] == ["text"]
    assert backend().items["a"].text == "Go Now"
    assert "b->c" in backend().edges
    assert backend().page["background"] == "#0F172A"


def test_bad_patch_op_is_a_warning(fake_server):
    call("render_diagram", {"spec": SPEC, "preview": False})
    res = call("patch_diagram", {"ops": [{"op": "remove", "id": "ghost"}], "preview": False})
    assert any("ghost" in w for w in json.loads(res.content[0].text)["warnings"])


def test_locked_file_saves_under_a_free_name(fake_server, monkeypatch):
    real_save = FakeVisio.save

    def save(self, path):
        if path.endswith("hello-world.vsdx"):
            raise PermissionError("in use")
        return real_save(self, path)

    monkeypatch.setattr(FakeVisio, "save", save)
    summary = json.loads(call("render_diagram", {"spec": SPEC, "preview": False}).content[0].text)
    assert summary["files"][0].endswith("hello-world-2.vsdx")
    assert any("open in another program" in w for w in summary["warnings"])


def test_export_forces_the_requested_format(fake_server):
    call("render_diagram", {"spec": SPEC, "preview": False})
    res = call("export_diagram", {"format": "pdf", "path": str(fake_server / "out.png")})
    assert res.content[0].text.endswith("out.pdf")


def test_open_rejects_non_visio_files(fake_server):
    (fake_server / "notes.txt").write_text("x")
    assert ".vsdx" in error("open_diagram", {"path": str(fake_server / "notes.txt")})


def test_rules_themes_kinds_and_lint_tools():
    rules = call("get_diagram_rules", {"diagram_type": "swimlane"}).content[0].text
    assert "lane" in rules.lower()
    assert "unknown" in error("get_diagram_rules", {"diagram_type": "nope"}).lower()
    themes = call("list_themes", {})
    assert "azure" in themes.content[0].text
    assert "aws-lambda" in call("list_kinds", {"provider": "aws"}).content[0].text
    lint = json.loads(call("lint_diagram", {"spec": SPEC}).content[0].text)
    assert lint["type"] == "flowchart" and lint["layout"] == "flowchart-tb"


def test_native_drawer_without_visio(fake_server, monkeypatch):
    monkeypatch.setattr(server, "_drawer", Drawer(target="native"))
    res = call("render_diagram", {"spec": SPEC, "formats": ["svg"], "preview": False})
    files = json.loads(res.content[0].text)["files"]
    assert files[0].endswith(".vsdx") and any(f.endswith(".svg") for f in files)
