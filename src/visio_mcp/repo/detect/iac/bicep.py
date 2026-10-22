"""Bicep: resources and modules from .bicep files."""

from __future__ import annotations

import re

from ...lists import add_unique
from .resource import resource


BICEP_RES = re.compile(r"^[ \t]*resource\s+(\w+)\s+'([^']+)'(\s+existing)?\s*=", re.M)
BICEP_MOD = re.compile(r"^[ \t]*module\s+(\w+)\s+'([^']+)'", re.M)


def parse_bicep(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    matches = list(BICEP_RES.finditer(text))
    for i, m in enumerate(matches):
        if m.group(3):  # existing
            continue
        rtype = m.group(2).split("@", 1)[0]
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)][:3000].lower()
        hint = "functionapp" if "functionapp" in body else ""
        out.append(resource("bicep", "azure", rtype, m.group(1), rel, hint))
        add_unique(clouds, "azure")
    for m in BICEP_MOD.finditer(text):
        out.append(resource("bicep", "azure", "module", m.group(1), rel, m.group(2)))
    add_unique(clouds, "azure")
