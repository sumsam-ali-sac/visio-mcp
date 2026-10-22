import pytest

from fake_visio import FakeVisio


@pytest.fixture
def fake() -> FakeVisio:
    return FakeVisio()
