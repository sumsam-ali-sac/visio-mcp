"""Icon names, install sources, lookup and removal against fake vendor packs."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from visio_mcp import catalog, icons
from visio_mcp.icons import sources

WHEEL = Path(os.environ.get(
    "VISIO_MCP_TEST_DIAGRAMS_WHEEL",
    "/tmp/claude-0/-home-user-visio-mcp/fc9490f4-6a06-5d3a-a400-d22d45c20015/scratchpad/iconsrc/"
    "diagrams-0.25.1-py3-none-any.whl"))


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


def test_install_from_diagrams_style_zip(tmp_path, make_zip, diagrams_names):
    src = make_zip(tmp_path / "diagrams-1.0-py3-none-any.whl", diagrams_names)
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


def test_install_official_folder_prefers_svg(tmp_path, png_bytes, svg_bytes):
    root = tmp_path / "Azure_Public_Service_Icons" / "Icons" / "compute"
    root.mkdir(parents=True)
    (root / "10029-icon-service-Function-Apps.svg").write_bytes(svg_bytes)
    (root / "function-apps.png").write_bytes(png_bytes())
    (root / "10035-icon-service-App-Services.svg").write_bytes(svg_bytes)
    done = icons.install("azure", source=str(tmp_path))
    assert done == {"azure": 2}
    assert icons.find("azure-functions").suffix == ".svg"


def test_install_official_aws_zip(tmp_path, make_zip):
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


def test_install_unknown_source_names_provider(tmp_path, make_zip):
    src = make_zip(tmp_path / "x.zip", ["foo/bar.png"])
    with pytest.raises(icons.IconInstallError) as e:
        icons.install(source=str(src))
    assert "azure|aws|gcp" in e.value.hint


def test_install_default_falls_back_to_pypi(tmp_path, monkeypatch, make_zip, diagrams_names):
    wheel = make_zip(tmp_path / "diagrams-9-py3-none-any.whl", diagrams_names)
    tried: list[str] = []
    monkeypatch.setattr(sources, "vendor_urls", lambda p: [f"https://vendor.invalid/{p}.zip"])

    def fake_download(url, dest, say):
        tried.append(url)
        raise OSError("403 Forbidden")

    monkeypatch.setattr(sources, "download", fake_download)
    monkeypatch.setattr(sources, "pypi_wheel", lambda say, tmp: wheel)
    done = icons.install("aws")
    assert done == {"aws": 3} and tried == ["https://vendor.invalid/aws.zip"]
    assert icons.status()["aws"]["source"].startswith("pypi:diagrams")


def test_install_nothing_works_is_friendly(monkeypatch):
    monkeypatch.setattr(sources, "vendor_urls", lambda p: [])

    def boom(say, tmp):
        raise OSError("offline")

    monkeypatch.setattr(sources, "pypi_wheel", boom)
    with pytest.raises(icons.IconInstallError) as e:
        icons.install("gcp")
    assert "visio-ai icons install gcp --from" in e.value.hint


def test_remove_and_missing_for(tmp_path, make_zip, diagrams_names):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    assert icons.missing_for(["aws-lambda", "azure-functions", "server"]) == []
    assert icons.remove("aws") == ["aws"]
    assert icons.missing_for(["aws-lambda", "azure-functions", "server"]) == ["aws"]
    assert icons.status()["aws"]["count"] == 0


def test_custom_icon_wins(tmp_path, make_zip, diagrams_names, svg_bytes):
    icons.install(source=str(make_zip(tmp_path / "d.whl", diagrams_names)))
    mine = tmp_path / "mine.svg"
    mine.write_bytes(svg_bytes)
    assert icons.resolve_image(str(mine), "aws-lambda") == mine.resolve()
    assert icons.resolve_image(None, "aws-lambda").name == "lambda.png"
    assert icons.resolve_image(str(tmp_path / "nope.png"), "aws-lambda") is None
    assert icons.resolve_image(None, "server") is None


def test_png_for_png_is_itself(tmp_path, png_bytes):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    assert icons.png_for(p) == p


# --- coverage against the real `diagrams` layout -----------------------------------------------


@pytest.mark.skipif(not WHEEL.is_file(), reason="diagrams wheel not available locally")
def test_every_cloud_kind_maps_to_an_icon_in_diagrams_pack(tmp_path, make_zip):
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
