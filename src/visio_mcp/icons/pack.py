"""Choosing icons out of a zip, folder or wheel and writing them as an installable pack."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from visio_mcp.icons import index
from visio_mcp.icons.http import MAX_DOWNLOAD_BYTES
from visio_mcp.icons.names import normalize
from visio_mcp.icons.paths import INDEX, cache_dir, provider_dir
from visio_mcp.icons.providers import IMAGE_EXTS

MAX_ICON_BYTES = 2_000_000

Entry = tuple[str, Callable[[], bytes]]  # (path inside the source, reader)


def zip_entries(z: zipfile.ZipFile, prefix: str = "", depth: int = 0,
                opened: ExitStack | None = None) -> Iterator[Entry]:
    """Image entries in a zip (and zips nested in it). Readers stay valid until `opened` closes."""
    for info in z.infolist():
        name = info.filename
        if info.is_dir() or "__MACOSX" in name or Path(name).name.startswith("."):
            continue
        low = name.lower()
        if low.endswith(".zip") and depth < 2 and info.file_size < MAX_DOWNLOAD_BYTES:
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(info)))
            except (zipfile.BadZipFile, OSError):
                continue
            if opened is not None:
                opened.enter_context(inner)
            yield from zip_entries(inner, prefix + name + "/", depth + 1, opened)
        elif low.endswith(IMAGE_EXTS) and info.file_size <= MAX_ICON_BYTES:
            yield prefix + name, (lambda z=z, info=info: z.read(info))


def dir_entries(root: Path) -> Iterator[Entry]:
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__MACOSX" in p.parts or p.name.startswith("."):
            continue
        low = p.name.lower()
        if low.endswith(".zip"):
            try:
                with zipfile.ZipFile(p) as z:
                    for name, read in zip_entries(z, p.relative_to(root).as_posix() + "/", 1):
                        data = read()
                        yield name, (lambda d=data: d)
            except (zipfile.BadZipFile, OSError):
                continue
        elif low.endswith(IMAGE_EXTS) and p.stat().st_size <= MAX_ICON_BYTES:
            yield p.relative_to(root).as_posix(), (lambda p=p: p.read_bytes())


def detect(names: list[str]) -> set[str]:
    """Which providers a source holds icons for, from its file names."""
    found: set[str] = set()
    for n in names:
        low = n.lower()
        m = re.search(r"(?:^|/)resources/(azure|aws|gcp)/", low)
        if m:
            found.add(m.group(1))
        elif "icon-service-" in low or "azure" in low:
            found.add("azure")
        elif re.search(r"(?:^|/)(arch|res)_", low) or "aws" in low or "amazon" in low:
            found.add("aws")
        elif "google" in low or "gcp" in low or "cloud_" in low or "cloud-" in low:
            found.add("gcp")
    return found


def _score(path: str) -> tuple:
    """Higher wins when two files normalize to the same key."""
    low = path.lower()
    size = 0
    m = re.search(r"[_-](\d{2,3})(?:@\dx)?(?:[_-](?:light|dark))?\.(?:svg|png)$", low)
    if m:
        size = int(m.group(1))
    return (
        low.endswith(".svg"),  # vector beats bitmap
        "dark" not in Path(low).name,  # light variants for light pages
        "/res_" not in low and not Path(low).name.startswith("res_"),  # service icon over resource icon
        "legacy" not in low,
        size,
        -low.count("/"),
    )


def select(entries: list[Entry], provider: str, wheel_layout: bool) -> dict[str, Entry]:
    chosen: dict[str, tuple[tuple, Entry]] = {}
    aliases: dict[str, tuple[tuple, Entry]] = {}
    for name, read in entries:
        low = name.lower()
        if wheel_layout:
            m = re.search(r"(?:^|/)resources/([a-z0-9]+)/", low)
            if not m or m.group(1) != provider:
                continue
        if "arch-category" in low or "arch_category" in low or "/category" in low:
            continue  # category tiles, not services
        key = normalize(name)
        if not key or not re.fullmatch(r"[a-z0-9-]+", key):
            continue
        score = _score(name)
        if key not in chosen or score > chosen[key][0]:
            chosen[key] = (score, (name, read))
        if provider == "gcp" and not wheel_layout:  # Google packs often name the folder after the product
            parent = normalize(Path(name).parent.name)
            if parent and parent not in ("svg", "png", "icons", "") and re.fullmatch(r"[a-z0-9-]+", parent):
                if parent not in aliases or score > aliases[parent][0]:
                    aliases[parent] = (score, (name, read))
    for key, val in aliases.items():
        chosen.setdefault(key, val)
    return {k: v[1] for k, v in chosen.items()}


def write_pack(provider: str, picked: dict[str, Entry], source: str) -> int:
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{provider}-", dir=root))
    try:
        files = tmp / "files"
        files.mkdir()
        icons: dict[str, str] = {}
        for key, (name, read) in sorted(picked.items()):
            ext = Path(name).suffix.lower()
            data = read()
            if ext == ".svg" and b"<svg" not in data[:4096].lower() and b"<svg" not in data.lower():
                continue
            if ext == ".png" and not data.startswith(b"\x89PNG"):
                continue
            (files / f"{key}{ext}").write_bytes(data)
            icons[key] = f"files/{key}{ext}"
        if not icons:
            raise OSError("no usable icons")
        meta = {"provider": provider, "source": source, "count": len(icons),
                "installed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "icons": icons}
        (tmp / INDEX).write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")
        dest = provider_dir(provider)
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
        index.forget(provider)
        return len(icons)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
