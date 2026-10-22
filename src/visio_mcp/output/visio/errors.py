"""Turn pywintypes.com_error into RuntimeErrors with a readable message."""

from __future__ import annotations

import functools
from typing import Any, Callable

import pywintypes


def message(exc: Exception) -> str:
    """Readable text for a COM error (no raw tuples)."""
    if isinstance(exc, pywintypes.com_error):
        info = exc.excepinfo
        if info and len(info) > 2 and info[2]:
            return str(info[2]).strip()
        return str(exc.strerror or exc.args[0]).strip()
    return str(exc)


def guard(fn: Callable) -> Callable:
    """Decorator: a com_error raised by fn becomes RuntimeError('Visio <fn> failed: ...')."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except pywintypes.com_error as e:
            raise RuntimeError(f"Visio {fn.__name__} failed: {message(e)}") from None

    return wrapper
