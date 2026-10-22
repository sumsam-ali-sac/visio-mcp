"""Terraform: resources and modules from .tf files."""

from __future__ import annotations

import re

from ...lists import add_unique
from ..cloud import CLOUD_PRETTY
from .resource import resource


TF_RES = re.compile(r'^[ \t]*resource\s+"([\w-]+)"\s+"([\w-]+)"\s*\{', re.M)
TF_MOD = re.compile(r'^[ \t]*module\s+"([\w-]+)"', re.M)
TF_ENGINE = re.compile(r'engine\s*=\s*"([\w-]+)"')


def parse_terraform(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    matches = list(TF_RES.finditer(text))
    for i, m in enumerate(matches):
        rtype, name = m.group(1), m.group(2)
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)][:4000]
        prefix = rtype.split("_", 1)[0]
        provider = {"azurerm": "azure", "azuread": "azure", "azapi": "azure", "aws": "aws", "google": "gcp"}.get(prefix, prefix)
        hint = ""
        if rtype in ("aws_db_instance", "aws_rds_cluster", "google_sql_database_instance"):
            if e := TF_ENGINE.search(body):
                hint = e.group(1).lower()
            elif "database_version" in body:
                hint = (re.search(r'database_version\s*=\s*"([\w]+)', body) or [None, ""])[1].lower()
        out.append(resource("terraform", provider, rtype, name, rel, hint))
        if provider in CLOUD_PRETTY:
            add_unique(clouds, provider)
    for m in TF_MOD.finditer(text):
        out.append(resource("terraform", "", "module", m.group(1), rel))
