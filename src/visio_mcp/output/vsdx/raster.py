"""Bitmaps for icons in the .vsdx: PNG as-is, SVG rasterized once into the icon cache."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from visio_mcp.icons.names import normalize
from visio_mcp.icons.paths import cache_dir
from visio_mcp.output.svg.raster import find_chromium

RASTER_PX = 256  # SVG icons are rasterized at this size for .vsdx bitmaps


def _png_target(svg: Path) -> Path:
    st = svg.stat()
    h = hashlib.sha1(f"{svg.resolve()}|{st.st_mtime_ns}|{st.st_size}|{RASTER_PX}".encode()).hexdigest()[:16]
    return cache_dir() / "_png" / f"{normalize(svg.name) or 'icon'}-{h}.png"


def _raster_playwright(jobs: list[tuple[Path, Path]]) -> None:
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    args = ["--no-sandbox", "--disable-gpu"]
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=args)
        except Exception:
            exe = find_chromium()
            if not exe:
                raise
            browser = pw.chromium.launch(executable_path=exe, args=args)
        try:
            page = browser.new_page(viewport={"width": RASTER_PX, "height": RASTER_PX})
            for src, dest in jobs:
                uri = "data:image/svg+xml;base64," + base64.b64encode(src.read_bytes()).decode()
                page.set_content(
                    "<!doctype html><style>html,body{margin:0;background:transparent}"
                    f"img{{display:block;width:{RASTER_PX}px;height:{RASTER_PX}px;object-fit:contain}}</style>"
                    f'<img src="{uri}">')
                page.wait_for_function("document.images[0].complete")
                dest.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(dest), omit_background=True,
                                clip={"x": 0, "y": 0, "width": RASTER_PX, "height": RASTER_PX})
        finally:
            browser.close()


def _raster_cairosvg(jobs: list[tuple[Path, Path]]) -> None:
    import cairosvg  # type: ignore[import-not-found]

    for src, dest in jobs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(src), write_to=str(dest), output_width=RASTER_PX, output_height=RASTER_PX)


def pngs_for(paths: list[Path]) -> dict[Path, Path | None]:
    """Bitmaps for icons (PNG as-is, SVG rasterized once into the cache). None where impossible."""
    out: dict[Path, Path | None] = {}
    jobs: list[tuple[Path, Path]] = []
    for p in dict.fromkeys(Path(x) for x in paths):
        if p.suffix.lower() == ".png":
            out[p] = p
            continue
        try:
            dest = _png_target(p)
        except OSError:
            out[p] = None
            continue
        out[p] = dest
        if not dest.is_file():
            jobs.append((p, dest))
    if jobs:
        for fn in (_raster_playwright, _raster_cairosvg):
            try:
                fn(jobs)
                break
            except Exception:
                continue
        for src, dest in jobs:
            if not dest.is_file():
                out[src] = None
    return out


def png_for(path: str | os.PathLike) -> Path | None:
    """A PNG for one icon; SVGs are rasterized via playwright/chromium or cairosvg."""
    return pngs_for([Path(path)])[Path(path)]
