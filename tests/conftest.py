import pytest

from fake_visio import FakeVisio


@pytest.fixture(autouse=True)
def _no_icon_packs(tmp_path_factory, monkeypatch):
    """Tests never see the user's downloaded cloud icons unless they install their own."""
    monkeypatch.setenv("VISIO_MCP_ICONS", str(tmp_path_factory.mktemp("icons")))


@pytest.fixture
def fake() -> FakeVisio:
    return FakeVisio()
