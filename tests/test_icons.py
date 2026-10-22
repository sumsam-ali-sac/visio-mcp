"""Cloud icon packs: names, mapping coverage, install sources, and drawing with icons."""

from __future__ import annotations

import json
import os
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from visio_mcp import catalog, icons, svg, vsdx_writer
from visio_mcp.plan import build_plan
from visio_mcp.render import render_spec
from visio_mcp.spec import DiagramSpec

WHEEL = Path(os.environ.get(
    "VISIO_MCP_TEST_DIAGRAMS_WHEEL",
    "/tmp/claude-0/-home-user-visio-mcp/fc9490f4-6a06-5d3a-a400-d22d45c20015/scratchpad/iconsrc/"
    "diagrams-0.25.1-py3-none-any.whl"))


def png_bytes(w: int = 4, h: int = 4) -> bytes:
    """A tiny valid RGBA PNG."""
    def chunk(t: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x80\xf0\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><rect width="18" height="18" fill="#0078D4"/></svg>'

# a handful of real file names from each source's naming scheme
DIAGRAMS_NAMES = [
    "resources/azure/compute/function-apps.png", "resources/azure/compute/app-services.png",
    "resources/azure/database/cosmos-db.png", "resources/aws/compute/lambda.png",
    "resources/aws/database/dynamodb.png", "resources/aws/network/route-53.png",
    "resources/gcp/compute/run.png", "resources/gcp/analytics/bigquery.png",
    "resources/onprem/client/user.png",
]


def make_zip(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, SVG if n.endswith(".svg") else png_bytes())
    return path


# --- names ------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,key", [
    ("10029-icon-service-Function-Apps.svg", "function-apps"),
    ("10011-icon-service-Azure-Cosmos-DB.svg", "cosmos-db"),
    ("Arch_AWS-Lambda_64.svg", "lambda"),
    ("Arch_Amazon-DynamoDB_48@5x.png", "dynamodb"),
    ("Arch_Amazon-Route-53_64.svg", "route-53"),
    ("Res_Amazon-VPC_NAT-Gateway_48_Light.svg", "vpc-nat-gateway"),
    ("Cloud-Run-512-color-rgb.svg", "cloud-run"),
    ("cloud_run.svg", "cloud-run"),
    ("lambda.png", "lambda"),
])
def test_normalize(name, key):
    assert icons.normalize(name) == key


def test_cache_dir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VISIO_MCP_ICONS", str(tmp_path / "x"))
    assert icons.cache_dir() == tmp_path / "x"


def test_every_cloud_kind_has_curated_names():
    cloud = [k.name for k in catalog.kinds().values() if k.provider]
    assert cloud and not [k for k in cloud if k not in icons.ICON_NAMES]


# --- install ----------------------------------------------------------------------------------


def test_install_from_diagrams_style_zip(tmp_path):
    src = make_zip(tmp_path / "diagrams-1.0-py3-none-any.whl", DIAGRAMS_NAMES)
    done = icons.install(source=str(src))
    assert set(done) == {"azure", "aws", "gcp"}
    assert done["azure"] == 3 and done["aws"] == 3 and done["gcp"] == 2  # onprem ignored
    st = icons.status()
    assert st["aws"]["count"] == 3 and st["aws"]["source"] == str(src.resolve()) and st["aws"]["installed_at"]
    assert icons.find("aws-lambda").name == "lambda.png"
    assert icons.find("dynamodb").name == "dynamodb.png"  # catalog alias
    assert icons.find("aws-route53").name == "route-53.png"
    assert icons.find("gcp-cloud-run").name == "run.png"
    assert icons.find("database") is None  # generic kinds keep geometric shapes
    index = json.loads((icons.cache_dir() / "aws" / "index.json").read_text())
    assert index["icons"]["lambda"] == "files/lambda.png"


def test_install_official_folder_prefers_svg(tmp_path):
    root = tmp_path / "Azure_Public_Service_Icons" / "Icons" / "compute"
    root.mkdir(parents=True)
    (root / "10029-icon-service-Function-Apps.svg").write_bytes(SVG)
    (root / "function-apps.png").write_bytes(png_bytes())
    (root / "10035-icon-service-App-Services.svg").write_bytes(SVG)
    done = icons.install("azure", source=str(tmp_path))
    assert done == {"azure": 2}
    assert icons.find("azure-functions").suffix == ".svg"


def test_install_official_aws_zip(tmp_path):
    names = ["Asset-Package/Architecture-Service-Icons/Arch_Compute/64/Arch_AWS-Lambda_64.svg",
             "Asset-Package/Architecture-Service-Icons/Arch_Compute/48/Arch_AWS-Lambda_48.svg",
             "Asset-Package/Architecture-Service-Icons/Arch_Compute/64/Arch_AWS-Lambda_64@5x.png",
             "Asset-Package/Category-Icons/Arch-Category_Compute_64.svg",
             "Asset-Package/Architecture-Service-Icons/Arch_Database/64/Arch_Amazon-DynamoDB_64.svg",
             "__MACOSX/._Arch_AWS-Lambda_64.svg"]
    src = make_zip(tmp_path / "Asset-Package.zip", names)
    assert icons.install(source=str(src)) == {"aws": 2}  # provider detected from the names
    assert icons.find("aws-lambda").name == "lambda.svg"
    assert icons.find("aws-dynamodb") is not None


def test_install_unknown_source_names_provider(tmp_path):
    src = make_zip(tmp_path / "x.zip", ["foo/bar.png"])
    with pytest.raises(icons.IconInstallError) as e:
        icons.install(source=str(src))
    assert "azure|aws|gcp" in e.value.hint


def test_install_default_falls_back_to_pypi(tmp_path, monkeypatch):
    wheel = make_zip(tmp_path / "diagrams-9-py3-none-any.whl", DIAGRAMS_NAMES)
    tried: list[str] = []
    monkeypatch.setattr(icons, "_vendor_urls", lambda p: [f"https://vendor.invalid/{p}.zip"])

    def fake_download(url, dest, say):
        tried.append(url)
        raise OSError("403 Forbidden")

    monkeypatch.setattr(icons, "_download", fake_download)
    monkeypatch.setattr(icons, "_pypi_wheel", lambda say, tmp: wheel)
    done = icons.install("aws")
    assert done == {"aws": 3} and tried == ["https://vendor.invalid/aws.zip"]
    assert icons.status()["aws"]["source"].startswith("pypi:diagrams")


def test_install_nothing_works_is_friendly(monkeypatch):
    monkeypatch.setattr(icons, "_vendor_urls", lambda p: [])

    def boom(say, tmp):
        raise OSError("offline")

    monkeypatch.setattr(icons, "_pypi_wheel", boom)
    with pytest.raises(icons.IconInstallError) as e:
        icons.install("gcp")
    assert "visio-ai icons install gcp --from" in e.value.hint


def test_remove_and_missing_for(tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    assert icons.missing_for(["aws-lambda", "azure-functions", "server"]) == []
    assert icons.remove("aws") == ["aws"]
    assert icons.missing_for(["aws-lambda", "azure-functions", "server"]) == ["aws"]
    assert icons.status()["aws"]["count"] == 0


def test_custom_icon_wins(tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    mine = tmp_path / "mine.svg"
    mine.write_bytes(SVG)
    assert icons.resolve_image(str(mine), "aws-lambda") == mine.resolve()
    assert icons.resolve_image(None, "aws-lambda").name == "lambda.png"
    assert icons.resolve_image(str(tmp_path / "nope.png"), "aws-lambda") is None
    assert icons.resolve_image(None, "server") is None


def test_png_for_png_is_itself(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    assert icons.png_for(p) == p


# --- coverage against the real `diagrams` layout -----------------------------------------------


@pytest.mark.skipif(not WHEEL.is_file(), reason="diagrams wheel not available locally")
def test_every_cloud_kind_maps_to_an_icon_in_diagrams_pack(tmp_path):
    with zipfile.ZipFile(WHEEL) as z:
        names = [n for n in z.namelist() if n.startswith("resources/") and n.endswith(".png")]
    src = make_zip(tmp_path / "diagrams-fake.whl", names)  # same names, tiny files
    icons.install(source=str(src))
    report, missing = [], []
    for k in catalog.kinds().values():
        if not k.provider:
            continue
        _, key, how = icons.explain(k.name)
        if key is None:
            missing.append(k.name)
        elif how != "curated" or k.name in icons.STAND_INS:
            report.append(f"{k.name} -> {key} ({how})")
    print("\npoorly mapped:", report or "none")
    assert missing == []


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


def test_plan_uses_installed_icons(tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    plan = build_plan(_cloud_spec())
    fn, db, svc = (plan.node(i) for i in ("fn", "db", "svc"))
    assert fn.image and fn.image.name == "lambda.png" and fn.geometry == "icon" and fn.icon
    assert db.image and svc.image is None and svc.geometry != "icon"
    assert not [w for w in plan.warnings if "official icons" in w]


def test_svg_embeds_image(tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    out = svg.render_svg(build_plan(_cloud_spec()))
    assert out.count("<image ") == 2 and 'xlink:href="data:image/png;base64,' in out
    assert 'preserveAspectRatio="xMidYMid meet"' in out


def test_svg_embeds_custom_svg_icon(tmp_path):
    mine = tmp_path / "mine.svg"
    mine.write_bytes(SVG)
    out = svg.render_svg(build_plan(_cloud_spec(icon=str(mine))))
    assert "data:image/svg+xml;base64," in out


def test_vsdx_writes_picture_shapes(tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
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


def test_vsdx_svg_icon_falls_back_to_glyph_without_rasterizer(tmp_path, monkeypatch):
    mine = tmp_path / "mine.svg"
    mine.write_bytes(SVG)
    monkeypatch.setattr(icons, "pngs_for", lambda paths: {Path(p): None for p in paths})
    path = vsdx_writer.write_vsdx(build_plan(_cloud_spec(icon=str(mine))), tmp_path / "d.vsdx")
    with zipfile.ZipFile(path) as z:
        page = z.read("visio/pages/page1.xml").decode()
    assert 'Type="Foreign"' not in page and "__glyph_fn" in page


def test_render_with_fake_imports_icons(fake, tmp_path):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    result = render_spec(fake, _cloud_spec())
    assert set(fake.images) == {"fn", "db"}
    assert fake.images["fn"].endswith("lambda.png")
    assert fake.items["fn"].master == "Image"
    assert fake.styles["fn"]["label_below"] and fake.styles["fn"]["keep_fill"]
    assert fake.items["fn"].text.startswith("Fn")
    assert fake.items["svc"].master != "Image"
    assert not [w for w in result.warnings if "official icons" in w]


def test_render_real_icon_master_beats_downloaded_icon(tmp_path):
    from fake_visio import DEFAULT_MASTERS, FakeVisio

    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))
    fake = FakeVisio({**DEFAULT_MASTERS, "AWSCOMPUTE_U.VSSX": ["AWS Lambda"]})
    render_spec(fake, _cloud_spec())
    assert fake.items["fn"].master == "AWS Lambda" and "fn" not in fake.images
    assert "db" in fake.images  # no DynamoDB master: the downloaded icon is used


def test_render_custom_icon_beats_master(tmp_path):
    from fake_visio import DEFAULT_MASTERS, FakeVisio

    mine = tmp_path / "mine.png"
    mine.write_bytes(png_bytes())
    fake = FakeVisio({**DEFAULT_MASTERS, "AWSCOMPUTE_U.VSSX": ["AWS Lambda"]})
    render_spec(fake, _cloud_spec(icon=str(mine)))
    assert fake.images["fn"] == str(mine.resolve())


def test_render_falls_back_when_import_fails(fake, tmp_path, monkeypatch):
    icons.install(source=str(make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)))

    def broken(*a, **k):
        raise RuntimeError("Visio drop_image failed: unsupported")

    monkeypatch.setattr(fake, "drop_image", broken)
    render_spec(fake, _cloud_spec())
    assert fake.items["fn"].master == catalog.FALLBACK.master
    assert fake.styles["fn"]["label_below"]


def test_cli_icons_status_and_install(tmp_path, capsys):
    from visio_mcp.cli import main

    src = make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)
    assert main(["icons"]) == 0
    assert main(["icons", "install", "aws", "--from", str(src)]) == 0
    assert icons.status()["aws"]["count"] == 3
    assert main(["icons", "remove", "aws"]) == 0
    assert icons.status()["aws"]["count"] == 0


def test_server_install_icons(tmp_path, monkeypatch):
    import asyncio

    from visio_mcp import server

    src = make_zip(tmp_path / "d.whl", DIAGRAMS_NAMES)
    real = icons.install
    monkeypatch.setattr(icons, "install", lambda provider=None: real(provider, str(src)))
    out = asyncio.run(server.install_icons("gcp"))
    assert out["installed"] == {"gcp": 2} and out["status"]["gcp"]["count"] == 2


