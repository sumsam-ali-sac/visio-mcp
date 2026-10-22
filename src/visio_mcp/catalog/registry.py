"""The kind registry: every kind keyed by name."""

from __future__ import annotations

from visio_mcp.catalog.cloud import CLOUD_KINDS
from visio_mcp.catalog.generic import GENERIC_KINDS
from visio_mcp.catalog.model import Kind

BY_NAME: dict[str, Kind] = {k.name: k for k in GENERIC_KINDS + CLOUD_KINDS}
