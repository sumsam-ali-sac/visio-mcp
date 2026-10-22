"""Result types, spacing constants and the flow frame shared by every layout engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from visio_mcp.style import GroupStyle

Point = tuple[float, float]

NODE_GAP = 0.5  # between neighbouring boxes in a rank
DUMMY_GAP = 0.25  # between a box and an edge lane
LANE_GAP = 0.18  # between two parallel edge lanes
RANK_GAP_TB = 0.9  # between ranks when the flow runs top to bottom
RANK_GAP_LR = 1.3  # between ranks when the flow runs left to right
COMPACT_GAP = 0.5  # between rows of a compact block (no edges inside)
TRACK_GAP = 0.15  # between parallel horizontal edge segments in one rank gap
LABEL_PT = 8.5  # edge label font size, for sizing rank gaps
LOOP = 0.3  # how far a self loop sticks out of its node


@dataclass
class Rect:
    """Axis-aligned box by center, inches, origin bottom-left."""

    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def bottom(self) -> float:
        return self.y - self.h / 2

    @property
    def top(self) -> float:
        return self.y + self.h / 2


@dataclass
class LayoutResult:
    nodes: dict[str, Rect]  # node footprints by node id
    groups: dict[str, Rect]  # group frames by group id (include padding and header band)
    routes: dict[int, list[Point]] = field(default_factory=dict)  # by index in spec.edges
    width: float = 0.0  # extent of everything; all coordinates lie in [0, width] x [0, height]
    height: float = 0.0
    direction: Literal["tb", "lr", "none"] = "tb"
    lane_header: Literal["top", "left"] | None = None  # swimlanes: where each lane's label band sits


@dataclass(frozen=True)
class Frame:
    """Flow coordinates -> page coordinates.

    Engines work in (u, v): u runs across a rank, v runs along the flow and grows downstream.
    Top-to-bottom maps u -> x and v -> -y; left-to-right maps v -> x and u -> -y, so the
    order inside a rank reads top to bottom. Results are shifted to the origin afterwards.
    """

    lr: bool = False

    def size(self, w: float, h: float) -> tuple[float, float]:
        """Page size -> (extent across the rank, extent along the flow)."""
        return (h, w) if self.lr else (w, h)

    def point(self, u: float, v: float) -> Point:
        return (v, -u) if self.lr else (u, -v)

    def rect(self, u: float, v: float, cw: float, ah: float) -> Rect:
        return Rect(v, -u, ah, cw) if self.lr else Rect(u, -v, cw, ah)

    def insets(self, st: GroupStyle) -> tuple[float, float, float, float]:
        """(u before, u after, v before, v after) a group frame adds around its members.

        The header band sits at the page top: v-before for top-to-bottom, u-before for
        left-to-right.
        """
        p, hh = st.padding, st.header_height
        if self.lr:
            return p + hh, p, p, p
        return p, p, p + hh, p
