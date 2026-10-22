"""Regenerate the README images from the real code.

    uv run --with playwright python scripts/gen_readme_assets.py

docs/images/studio.svg   a recorded visio-ai studio session (the real UI components)
docs/images/themes.png   one example drawn in every theme
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "tests"))  # FakeVisio: records the Visio calls the studio would make


def _workspace(root: Path) -> Path:
    """A small multi-repo workspace: an API, a web frontend and AWS infrastructure."""
    shop = root / "shop"
    files = {
        "orders-api/pyproject.toml": '[project]\nname = "orders-api"\ndependencies = ["fastapi", "sqlalchemy", '
                                     '"psycopg2-binary", "redis", "kafka-python", "stripe"]\n',
        "orders-api/app/main.py": 'import os\nfrom fastapi import FastAPI\nDATABASE_URL = os.environ["DATABASE_URL"]\n'
                                  "app = FastAPI()\n",
        "orders-api/docker-compose.yml": "services:\n  api:\n    build: .\n    ports: ['8000:8000']\n"
                                         "    depends_on: [db, cache, kafka]\n  db:\n    image: postgres:16\n"
                                         "  cache:\n    image: redis:7\n  kafka:\n    image: bitnami/kafka:3.7\n",
        "orders-api/Dockerfile": "FROM python:3.12\n",
        "orders-api/.github/workflows/ci.yml": "on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
                                               "    steps: [{run: pytest}]\n",
        "storefront/package.json": '{"name": "storefront", "dependencies": {"next": "15.0.0", "react": "19.0.0"}}\n',
        "storefront/src/app/page.tsx": "export const API = process.env.NEXT_PUBLIC_ORDERS_API_URL;\n",
        "infra/main.tf": 'provider "aws" { region = "us-east-1" }\nresource "aws_vpc" "main" {}\n'
                         'resource "aws_ecs_service" "orders" {}\nresource "aws_db_instance" "orders" {}\n'
                         'resource "aws_elasticache_cluster" "cache" {}\nresource "aws_s3_bucket" "assets" {}\n'
                         'resource "aws_cloudfront_distribution" "web" {}\n',
    }
    for rel, text in files.items():
        p = shop / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for repo in ("orders-api", "storefront", "infra"):
        (shop / repo / ".git").mkdir(exist_ok=True)
    return shop


def _answer(question: str, answer: str) -> Text:
    """How a questionary prompt looks once answered."""
    from visio_mcp.cli import ui

    return Text.assemble(("◆ ", f"bold {ui.ACCENT}"), (question + " ", "bold"), (answer, f"bold {ui.ACCENT2}"))


def studio_svg(out: Path) -> None:
    from fake_visio import FakeVisio

    from visio_mcp import catalog
    from visio_mcp.ai.config import ProviderConfig
    from visio_mcp.cli import ui
    from visio_mcp.cli.studio import drawing, explore
    from visio_mcp.cli.studio.session import Session, provider_label
    from visio_mcp.output.drawer import Drawer

    console = ui.console  # every module prints through this one console, so record it
    console.record = True
    console.width = 104
    with tempfile.TemporaryDirectory() as tmp:
        shop = _workspace(Path(tmp))
        masters: dict[str, list[str]] = {}
        for kind in catalog.kinds().values():  # every built-in master the catalog knows, as a Visio install has
            for shape in kind.candidates:
                masters.setdefault(shape.stencil.upper(), []).append(shape.master)
        drawer = Drawer(backend=FakeVisio(masters))
        s = Session(theme="aws", out_dir=Path(tmp) / "out")

        ui.banner()
        cfg = ProviderConfig(provider="anthropic", model="claude-opus-5-5")
        console.print(ui.kv_table([("Output", Text("● Visio desktop — drawing live", style="good")),
                                   ("AI", Text(f"● {provider_label(cfg)}", style="good"))]))
        ui.step(1, 4, "Where is the code?")
        console.print(_answer("Folder path", r"C:\code\shop"))
        s.repos = explore.scan_paths(str(shop))
        console.print(explore.repo_table(s.repos))
        ui.step(2, 4, "What should we draw?")
        s.diagram_type = "cloud"
        console.print(_answer("Diagram type", "★ cloud"))
        console.print(_answer("Anything to focus on?", "the order flow"))
        ui.step(3, 4, "Explore the code")
        console.print(_answer("How should we explore the code?", "Quick draft without AI"))
        s.spec = explore.offline_draft(s.repos, s.diagram_type)
        console.print(ui.panel(drawing.spec_tree(s.spec), title="Draft"))
        ui.step(4, 4, "Draw")
        console.print(_answer("Theme", "★ aws"))
        result = drawing.draw(drawer, s)
        console.print(drawing.result_panel(result))
        console.print()
        ui.hint("Refine it: describe a change in plain words, or type /help.")
        console.print(_answer("✎", "group the data stores and make Orders the focus"))
        svg = console.export_svg(title="visio-ai")
    svg = svg.replace(str(Path(tmp) / "out"), r"C:\Users\you\Documents\visio-mcp")
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


def themes_png(out: Path) -> None:
    from visio_mcp.output.svg import render_svg
    from visio_mcp.plan import build_plan
    from visio_mcp.spec import DiagramSpec
    from visio_mcp.style import THEMES

    spec = DiagramSpec.model_validate(json.loads((ROOT / "examples" / "web-architecture.json").read_text()))
    cells = []
    for name in THEMES:
        svg = render_svg(build_plan(spec.model_copy(update={"theme": name, "legend": False})))
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
        cells.append(f'<figure><img src="{uri}"><figcaption>{name}</figcaption></figure>')
    html = ("<!doctype html><style>body{margin:0;padding:24px;background:#fff;font:600 15px 'Segoe UI',Arial}"
            "main{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;width:1400px}"
            "figure{margin:0;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}"
            "img{display:block;width:100%}figcaption{padding:8px 12px;color:#334155;background:#f8fafc;"
            "border-top:1px solid #e2e8f0}</style><main>" + "".join(cells) + "</main>")
    from playwright.sync_api import sync_playwright

    from visio_mcp.output.svg import find_chromium

    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "themes.html"
        page_file.write_text(html, encoding="utf-8")
        with sync_playwright() as pw:
            exe = find_chromium()
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}), args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1448, "height": 800}, device_scale_factor=1.5)
            page.goto(page_file.as_uri())
            page.locator("main").screenshot(path=str(out))
            browser.close()
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    IMAGES.mkdir(parents=True, exist_ok=True)
    studio_svg(IMAGES / "studio.svg")
    themes_png(IMAGES / "themes.png")
    subprocess.run(["git", "-C", str(ROOT), "status", "--short", "docs/images"], check=False)
