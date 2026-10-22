"""Fixtures that build tiny fake icon packs (zips with the names real vendor packs use)."""

from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path
from typing import Callable

import pytest

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><rect width="18" height="18" fill="#0078D4"/></svg>'

# a handful of real file names from each source's naming scheme
DIAGRAMS_NAMES = [
    "resources/azure/compute/function-apps.png", "resources/azure/compute/app-services.png",
    "resources/azure/database/cosmos-db.png", "resources/aws/compute/lambda.png",
    "resources/aws/database/dynamodb.png", "resources/aws/network/route-53.png",
    "resources/gcp/compute/run.png", "resources/gcp/analytics/bigquery.png",
    "resources/onprem/client/user.png",
]


def _png_bytes(w: int = 4, h: int = 4) -> bytes:
    """A tiny valid RGBA PNG."""
    def chunk(t: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x80\xf0\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _make_zip(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, SVG if n.endswith(".svg") else _png_bytes())
    return path


@pytest.fixture
def png_bytes() -> Callable[..., bytes]:
    return _png_bytes


@pytest.fixture
def make_zip() -> Callable[[Path, list[str]], Path]:
    return _make_zip


@pytest.fixture
def diagrams_names() -> list[str]:
    return list(DIAGRAMS_NAMES)


@pytest.fixture
def svg_bytes() -> bytes:
    return SVG
