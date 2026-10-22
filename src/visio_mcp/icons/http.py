"""HTTP helpers for downloading icon packs with a size cap and progress messages."""

from __future__ import annotations

import os
import ssl
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

MAX_DOWNLOAD_BYTES = 400_000_000
UA = "visio-mcp (https://github.com/; icon installer) Python-urllib"

Progress = Callable[[str], None]


def ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.isfile(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def open_url(url: str, timeout: float = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


def fetch_text(url: str, timeout: float = 20) -> str:
    with open_url(url, timeout) as r:
        return r.read(8_000_000).decode("utf-8", "replace")


def download(url: str, dest: Path, say: Progress) -> Path:
    with open_url(url, 60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_DOWNLOAD_BYTES:
                raise OSError("download too large")
            f.write(chunk)
            now = time.monotonic()
            if now - last > 0.25:
                last = now
                pct = f" {done * 100 // total}%" if total else ""
                say(f"Downloading {Path(url.split('?')[0]).name}{pct} ({done >> 20} MB)")
    return dest
