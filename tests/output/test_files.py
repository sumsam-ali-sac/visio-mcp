"""Output file helpers: names, folder, locked-file fallback, Visio detection."""

from pathlib import Path

import pytest

from visio_mcp.output import drawer
from visio_mcp.output.detect import visio_available
from visio_mcp.output.files import default_out_dir, free_name, save_free, slug


def test_slug():
    assert slug("Orders Platform: v2!") == "orders-platform-v2"
    assert slug("***") == "diagram"


def test_default_out_dir_from_env(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b"
    monkeypatch.setenv("VISIO_MCP_OUT", str(target))
    assert default_out_dir() == target and target.is_dir()


def test_free_name_skips_existing_files(tmp_path):
    p = tmp_path / "d.vsdx"
    assert free_name(p) == tmp_path / "d-2.vsdx"
    (tmp_path / "d-2.vsdx").touch()
    assert free_name(p) == tmp_path / "d-3.vsdx"


def test_save_free(tmp_path):
    seen: list[Path] = []

    def save(p: Path) -> Path:
        seen.append(p)
        if p.name == "d.vsdx":
            raise PermissionError("locked")
        return p

    assert save_free(lambda p: p, tmp_path / "x.vsdx") == (tmp_path / "x.vsdx", None)
    saved, warning = save_free(save, tmp_path / "d.vsdx")
    assert saved == tmp_path / "d-2.vsdx" and seen == [tmp_path / "d.vsdx", saved]
    assert warning == "d.vsdx is open in another program; saved as d-2.vsdx"


def test_visio_is_not_available_off_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert visio_available() is False


@pytest.mark.parametrize("name", ["Drawer", "DrawOutput", "slug", "default_out_dir", "open_file", "visio_available"])
def test_drawer_module_keeps_the_names_cli_and_mcp_use(name):
    assert hasattr(drawer, name)
