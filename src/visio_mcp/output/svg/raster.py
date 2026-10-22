"""svg_to_png: best-effort rasterization with playwright/chromium, then cairosvg."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

CHROMIUM_GLOBS = ("chromium-*/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell",
                  "chromium-*/chrome-linux64/chrome", "chromium-*/chrome-win/chrome.exe",
                  "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium")


def svg_to_png(svg_path: str | os.PathLike, png_path: str | os.PathLike, scale: float = 2.0) -> Path | None:
    """Rasterize an SVG file. Tries playwright/chromium, then cairosvg; returns None if neither works."""
    try:
        src = Path(svg_path)
        out = Path(png_path)
        svg = src.read_text(encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    for fn in (_png_playwright, _png_cairosvg):
        try:
            if fn(svg, out, scale):
                return out
        except Exception:
            continue
    return None


def find_chromium() -> str | None:
    """A chromium binary from a playwright browsers folder, when playwright's own lookup fails."""
    for root in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers"):
        if not root or not os.path.isdir(root):
            continue
        for pat in CHROMIUM_GLOBS:
            hits = sorted(Path(root).glob(pat))
            if hits:
                return str(hits[-1])
    return None


def _svg_size(svg: str) -> tuple[float, float]:
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if m:
        return float(m.group(1)), float(m.group(2))
    return 1200.0, 800.0


def _png_playwright(svg: str, png_path: Path, scale: float) -> bool:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except Exception:
        return False
    w, h = _svg_size(svg)
    page_html = ("<!doctype html><meta charset=utf-8><style>html,body{margin:0;padding:0;background:transparent}"
                 "svg{display:block}</style>" + re.sub(r"^<\?xml[^>]*\?>", "", svg))
    with sync_playwright() as pw:
        browser = None
        args = ["--no-sandbox", "--disable-gpu"]
        try:
            browser = pw.chromium.launch(args=args)
        except Exception:
            exe = find_chromium()
            if exe:
                browser = pw.chromium.launch(executable_path=exe, args=args)
        if browser is None:
            return False
        try:
            ctx = browser.new_context(viewport={"width": max(1, math.ceil(w)), "height": max(1, math.ceil(h))},
                                      device_scale_factor=scale)
            page = ctx.new_page()
            page.set_content(page_html)
            page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": w, "height": h})
        finally:
            browser.close()
    return png_path.exists()


def _png_cairosvg(svg: str, png_path: Path, scale: float) -> bool:
    try:
        import cairosvg  # type: ignore[import-not-found]
    except Exception:
        return False
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), scale=scale)
    return png_path.exists()
