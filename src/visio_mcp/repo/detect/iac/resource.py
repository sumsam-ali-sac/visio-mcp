"""The common shape of an IaC resource record."""

from __future__ import annotations


def resource(iac: str, provider: str, rtype: str, name: str, file: str, hint: str = "") -> dict:
    return {"iac": iac, "provider": provider, "type": rtype, "name": name, "file": file, "hint": hint}
