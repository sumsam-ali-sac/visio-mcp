"""Find, name and classify shapes on a page by their universal name."""

from __future__ import annotations

from typing import Any

import pywintypes


def find(page: Any, name: str) -> Any:
    try:
        return page.Shapes.ItemU(name)
    except pywintypes.com_error:
        raise KeyError(f"no shape named {name!r}") from None


def find_opt(page: Any, name: str) -> Any | None:
    try:
        return page.Shapes.ItemU(name)
    except pywintypes.com_error:
        return None


def check_new(page: Any, name: str) -> None:
    if find_opt(page, name) is not None:
        raise KeyError(f"duplicate shape name {name!r}")


def set_name(shape: Any, name: str) -> None:
    shape.Name = name
    shape.NameU = name


def is_container(shape: Any) -> bool:
    cell = "User.msvStructureType"
    return bool(shape.CellExistsU(cell, 0)) and "Container" in shape.CellsU(cell).FormulaU
