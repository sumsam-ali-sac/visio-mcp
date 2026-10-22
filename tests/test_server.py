"""Tools called through the MCP layer, the way a client sees them (fake backend)."""

import asyncio
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from fake_visio import FakeVisio
from visio_mcp import server

SPEC = {
    "title": "Hello World",
    "nodes": [{"id": "a", "kind": "process"}, {"id": "b", "kind": "decision"}],
    "edges": [{"source": "a", "target": "b"}],
}


@pytest.fixture(autouse=True)
def fake_server(monkeypatch, tmp_path):
    monkeypatch.setenv("VISIO_MCP_OUT", str(tmp_path))
    monkeypatch.setattr(server, "_backend", FakeVisio())
    monkeypatch.setattr(server, "_current", {"vsdx": None, "formats": ["png"]})
    return tmp_path


def call(name, args):
    return asyncio.run(server.mcp.call_tool(name, args))


def error(name, args) -> str:
    """The message a client sees for a failing call (MCP sends ToolError text, hides others)."""
    with pytest.raises(ToolError) as exc:
        call(name, args)
    return str(exc.value)


def test_render_returns_summary_and_preview_image(fake_server):
    res = call("render_diagram", {"spec": SPEC})
    assert not res.is_error, res.content
    assert [c.type for c in res.content] == ["text", "image"]
    summary = json.loads(res.content[0].text)
    assert summary["shapes"] == 2 and summary["connectors"] == 1
    assert summary["files"][0] == str(fake_server / "hello-world.vsdx")


def test_invalid_spec_is_a_readable_error():
    assert "unknown nodes" in error("render_diagram", {"spec": {**SPEC, "edges": [{"source": "a", "target": "zz"}]}})


def test_patch_before_render_is_an_error():
    assert "no diagram open" in error("patch_diagram", {"ops": [{"op": "relayout", "layout": "radial"}]})


def test_patch_after_render(fake_server):
    call("render_diagram", {"spec": SPEC, "preview": False})
    res = call("patch_diagram", {"ops": [{"op": "update_node", "id": "a", "label": "Go"}], "preview": False})
    assert not res.is_error
    assert [c.type for c in res.content] == ["text"]
    assert server._backend.items["a"].text == "Go"


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
