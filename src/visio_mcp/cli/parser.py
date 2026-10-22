"""The visio-ai argument parser: every command and flag, no behavior."""

from __future__ import annotations

import argparse

from visio_mcp.rules import TYPES

PROVIDERS = ["anthropic", "openai", "azure", "gemini", "ollama"]
CLOUDS = ["azure", "aws", "gcp"]


def _output_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--theme", help="professional, azure, aws, gcp, c4, blueprint, dark, monochrome")
    sp.add_argument("--out", help="output folder (default: Documents/visio-mcp)")
    sp.add_argument("--native", action="store_true", help="write .vsdx without Visio")
    sp.add_argument("--no-live", action="store_true", help="draw in a hidden Visio instead of live")
    sp.add_argument("--attach", action="store_true", help="draw into the Visio window you already have open")
    sp.add_argument("--format", action="append", dest="formats", help="png, svg, pdf, html (repeatable)")
    sp.add_argument("--no-open", action="store_true", help="don't open the result")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="visio-ai", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command")

    st = sub.add_parser("studio", add_help=False)
    st.add_argument("path", nargs="?")
    st.add_argument("--type", choices=TYPES)
    st.add_argument("--focus", default="")
    _output_flags(st)

    d = sub.add_parser("draw")
    d.add_argument("path")
    d.add_argument("--type", choices=TYPES)
    d.add_argument("--focus", default="", help="what to emphasise, in plain words")
    d.add_argument("--provider", choices=PROVIDERS)
    d.add_argument("--model")
    d.add_argument("--offline", action="store_true", help="no AI: draft from a static scan")
    d.add_argument("--save-spec", help="also save the spec JSON here")
    _output_flags(d)

    r = sub.add_parser("render")
    r.add_argument("spec")
    _output_flags(r)

    sc = sub.add_parser("scan")
    sc.add_argument("path")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--digest", action="store_true", help="print the AI digest")

    sub.add_parser("setup")
    h = sub.add_parser("handoff")
    h.add_argument("path")
    h.add_argument("--tool", choices=["claude", "gemini", "codex", "copilot"])
    h.add_argument("--type", choices=TYPES, default="architecture")
    h.add_argument("--focus", default="")
    sub.add_parser("doctor")
    ic = sub.add_parser("icons")
    ic.add_argument("action", nargs="?", choices=["status", "install", "remove"], default="status")
    ic.add_argument("provider", nargs="?", choices=[*CLOUDS, "all"], default="all")
    ic.add_argument("--from", dest="source", help="official icon zip, folder or URL you downloaded")
    sub.add_parser("themes")
    k = sub.add_parser("kinds")
    k.add_argument("--provider", choices=CLOUDS)
    ru = sub.add_parser("rules")
    ru.add_argument("type", choices=TYPES)
    ru.add_argument("--provider", choices=CLOUDS)
    _output_flags(sub.add_parser("examples"))
    sub.add_parser("mcp")
    return p
