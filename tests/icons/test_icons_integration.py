"""Cloud icons flowing through plan, svg, vsdx, Visio render, the CLI and the MCP server."""

from __future__ import annotations

import zipfile
from pathlib import Path

from visio_mcp import catalog, icons
from visio_mcp.output import svg
from visio_mcp.output import vsdx as vsdx_writer
from visio_mcp.output.visio.draw import render_spec
from visio_mcp.plan import build_plan
from visio_mcp.spec import DiagramSpec

# --- drawing ----------------------------------------------------------------------------------


def _cloud_spec(**node) -> DiagramSpec:
    return DiagramSpec.model_validate({
        "title": "T", "type": "cloud",
        "nodes": [{"id": "fn", "label": "Fn", "kind": "aws-lambda", **node},
                  {"id": "db", "label": "Table", "kind": "aws-dynamodb"},
                  {"id": "svc", "label": "Service", "kind": "service"}],
        "edges": [{"source": "fn", "target": "db"}, {"source": "svc", "target": "fn"}],
    })


def test_plan_warns_once_without_icons():
    plan = build_plan(_cloud_spec())
    msgs = [w for w in plan.warnings if "official icons" in w]
    assert len(msgs) == 1 and "2 AWS services" in msgs[0] and "visio-ai icons install" in msgs[0]
    assert all(n.image is None for n in plan.nodes)


def test_plan_uses_installed_icons(tmp_path, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    plan = build_plan(_cloud_spec())
    fn, db, svc = (plan.node(i) for i in ("fn", "db", "svc"))
    assert fn.image and fn.image.name == "lambda.png" and fn.geometry == "icon" and fn.icon
    assert db.image and svc.image is None and svc.geometry != "icon"
    assert not [w for w in plan.warnings if "official icons" in w]


def test_svg_embeds_image(tmp_path, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    out = svg.render_svg(build_plan(_cloud_spec()))
    assert out.count("<image ") == 2 and 'xlink:href="data:image/png;base64,' in out
    assert 'preserveAspectRatio="xMidYMid meet"' in out


def test_svg_embeds_custom_svg_icon(tmp_path, svg_bytes):
    mine = tmp_path / "mine.svg"
    mine.write_bytes(svg_bytes)
    out = svg.render_svg(build_plan(_cloud_spec(icon=str(mine))))
    assert "data:image/svg+xml;base64," in out


def test_vsdx_writes_picture_shapes(tmp_path, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    path = vsdx_writer.write_vsdx(build_plan(_cloud_spec()), tmp_path / "d.vsdx")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "visio/media/image1.png" in names and "visio/media/image2.png" in names
        assert z.read("visio/media/image1.png").startswith(b"\x89PNG")
        ct = z.read("[Content_Types].xml").decode()
        assert '<Default Extension="png" ContentType="image/png"/>' in ct
        rels = z.read("visio/pages/_rels/page1.xml.rels").decode()
        assert 'Target="../media/image1.png"' in rels and "relationships/image" in rels
        page = z.read("visio/pages/page1.xml").decode()
        assert page.count('Type="Foreign"') == 2
        assert '<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="rId1"/></ForeignData>' in page
        assert 'NameU="fn"' in page and 'NameU="__icon_fn"' in page


def test_vsdx_without_icons_has_no_media(tmp_path):
    path = vsdx_writer.write_vsdx(build_plan(_cloud_spec()), tmp_path / "d.vsdx")
    with zipfile.ZipFile(path) as z:
        assert not [n for n in z.namelist() if "media" in n]
        assert 'Extension="png"' not in z.read("[Content_Types].xml").decode()


def test_vsdx_svg_icon_falls_back_to_glyph_without_rasterizer(tmp_path, monkeypatch, svg_bytes):
    mine = tmp_path / "mine.svg"
    mine.write_bytes(svg_bytes)
    monkeypatch.setattr(icons, "pngs_for", lambda paths: {Path(p): None for p in paths})
    path = vsdx_writer.write_vsdx(build_plan(_cloud_spec(icon=str(mine))), tmp_path / "d.vsdx")
    with zipfile.ZipFile(path) as z:
        page = z.read("visio/pages/page1.xml").decode()
    assert 'Type="Foreign"' not in page and "__glyph_fn" in page


def test_render_with_fake_imports_icons(fake, tmp_path, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    result = render_spec(fake, _cloud_spec())
    assert set(fake.images) == {"fn", "db"}
    assert fake.images["fn"].endswith("lambda.png")
    assert fake.items["fn"].master == "Image"
    assert fake.styles["fn"]["label_below"] and fake.styles["fn"]["keep_fill"]
    assert fake.items["fn"].text.startswith("Fn")
    assert fake.items["svc"].master != "Image"
    assert not [w for w in result.warnings if "official icons" in w]


def test_render_real_icon_master_beats_downloaded_icon(tmp_path, make_zip, diagrams_names):
    from fake_visio import DEFAULT_MASTERS, FakeVisio

    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    fake = FakeVisio({**DEFAULT_MASTERS, "AWSCOMPUTE_U.VSSX": ["AWS Lambda"]})
    render_spec(fake, _cloud_spec())
    assert fake.items["fn"].master == "AWS Lambda" and "fn" not in fake.images
    assert "db" in fake.images  # no DynamoDB master: the downloaded icon is used


def test_render_custom_icon_beats_master(tmp_path, png_bytes):
    from fake_visio import DEFAULT_MASTERS, FakeVisio

    mine = tmp_path / "mine.png"
    mine.write_bytes(png_bytes())
    fake = FakeVisio({**DEFAULT_MASTERS, "AWSCOMPUTE_U.VSSX": ["AWS Lambda"]})
    render_spec(fake, _cloud_spec(icon=str(mine)))
    assert fake.images["fn"] == str(mine.resolve())


def test_render_falls_back_when_import_fails(fake, tmp_path, monkeypatch, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))

    def broken(*a, **k):
        raise RuntimeError("Visio drop_image failed: unsupported")

    monkeypatch.setattr(fake, "drop_image", broken)
    render_spec(fake, _cloud_spec())
    assert fake.items["fn"].master == catalog.FALLBACK.master
    assert fake.styles["fn"]["label_below"]


def test_cli_icons_status_and_install(tmp_path, capsys, make_zip, diagrams_names):
    from visio_mcp.cli.main import main

    src = make_zip(tmp_path / "d.whl", diagrams_names)
    assert main(["icons"]) == 0
    assert main(["icons", "install", "aws", "--from", str(src)]) == 0
    assert icons.status()["aws"]["count"] == 3
    assert main(["icons", "remove", "aws"]) == 0
    assert icons.status()["aws"]["count"] == 0


def test_server_install_icons(tmp_path, monkeypatch, make_zip, diagrams_names):
    import asyncio

    from visio_mcp.mcp import server

    src = make_zip(tmp_path / "d.whl", diagrams_names)
    real = icons.install
    monkeypatch.setattr(icons, "install", lambda provider=None: real(provider, str(src)))
    out = asyncio.run(server.install_icons("gcp"))
    assert out["installed"] == {"gcp": 2} and out["status"]["gcp"]["count"] == 2
