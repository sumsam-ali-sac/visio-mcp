"""VisioBackend implemented with Visio desktop over COM.  (F2: implement)"""

from __future__ import annotations


class VisioCom:
    """Implements visio_mcp.backend.VisioBackend. Create and use only on the COM thread."""

    def __init__(self, visible: bool = False) -> None:
        raise NotImplementedError
