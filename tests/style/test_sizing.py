"""Node footprints."""

from __future__ import annotations

import pytest

from visio_mcp.style import GEOMETRY_MIN, ICON_SIZE, node_size


@pytest.mark.parametrize("geometry", [g for g in GEOMETRY_MIN if g not in ("icon", "person")])
def test_shapes_never_shrink_below_their_minimum(geometry):
    s = node_size(geometry, "X")
    min_w, min_h = GEOMETRY_MIN[geometry]
    assert s.w >= min_w and s.h >= min_h
    assert (s.shape_w, s.shape_h) == (s.w, s.h) and s.dy == 0


def test_sizes_snap_to_eighth_inch():
    s = node_size("rounded", "A fairly long label that wraps", "Tech", "A description line")
    assert s.w * 8 == round(s.w * 8) and s.h * 8 == round(s.h * 8)


def test_more_text_means_a_bigger_node():
    small = node_size("rounded", "Api")
    big = node_size("rounded", "Api", "FastAPI", "Handles every order request from the storefront")
    assert big.h > small.h


def test_circle_is_square():
    s = node_size("circle", "Start here please")
    assert s.w == s.h


@pytest.mark.parametrize("geometry", ["icon", "person"])
def test_icons_keep_a_square_master_above_the_label(geometry):
    s = node_size(geometry, "Customer", "Browser")
    assert s.shape_w == s.shape_h == ICON_SIZE
    assert s.h > ICON_SIZE and s.dy > 0

