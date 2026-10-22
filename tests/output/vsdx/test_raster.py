"""Icon bitmaps for the .vsdx: PNGs pass through, SVGs are rasterized into the icon cache."""

from pathlib import Path

from visio_mcp.output.vsdx import raster


def test_png_is_used_as_is(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert raster.png_for(p) == p


def test_svg_without_rasterizer_is_none(tmp_path, monkeypatch):
    svg = tmp_path / "icon.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")

    def fail(jobs):
        raise RuntimeError("no rasterizer")

    monkeypatch.setattr(raster, "_raster_playwright", fail)
    monkeypatch.setattr(raster, "_raster_cairosvg", fail)
    assert raster.pngs_for([svg]) == {Path(svg): None}


def test_rasterized_files_land_in_the_icon_cache(tmp_path, monkeypatch):
    svg = tmp_path / "Function-Apps.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")

    def fake(jobs):
        for _src, dest in jobs:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(raster, "_raster_playwright", fake)
    out = raster.png_for(svg)
    assert out is not None and out.is_file() and out.parent.name == "_png"
    assert raster.png_for(svg) == out  # cached
