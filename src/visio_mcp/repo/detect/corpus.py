"""The text corpus (env examples, app config, compose, sample sources) that keyword detection searches."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..text import read_text
from .classify import Inventory


@dataclass(slots=True)
class Corpus:
    blob: str  # all text concatenated
    env_lines: list[str]  # KEY=value lines from env example files
    env_keys: str  # upper-cased env variable names, newline separated


def build_corpus(root: Path, inv: Inventory, compose_text: str) -> Corpus:
    env_lines: list[str] = []
    blob_parts: list[str] = [compose_text]
    for rel in inv.env_examples[:6] + inv.configs[:10]:
        text = read_text(root / rel, 40_000)
        blob_parts.append(text)
        if rel in inv.env_examples[:6]:
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_lines.append(k.strip() + "=" + v.strip().strip("\"'"))
    for f in sorted(inv.samples, key=lambda f: (f.depth, f.rel))[:150]:
        blob_parts.append(read_text(root / f.rel, 16_000))
    env_keys = "\n".join(l.split("=", 1)[0].upper() for l in env_lines)
    env_keys += "\n" + "\n".join(re.findall(r"^\s*-?\s*([A-Z][A-Z0-9_]{3,})\s*[:=]", compose_text, re.M))
    return Corpus("\n".join(blob_parts), env_lines, env_keys)
