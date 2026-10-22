"""Run all Visio COM calls on one thread.

COM objects belong to the thread (apartment) that created them, and MCP tools
run on arbitrary worker threads. A single-worker executor that calls
CoInitialize once keeps every Visio call on the same thread.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _init_com() -> None:
    try:
        import pythoncom
    except ImportError:  # non-Windows / tests: nothing to initialize
        return
    pythoncom.CoInitialize()


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="visio-com", initializer=_init_com)


async def call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Await fn(*args, **kwargs) running on the COM thread."""
    return await asyncio.wrap_future(_executor.submit(fn, *args, **kwargs))
