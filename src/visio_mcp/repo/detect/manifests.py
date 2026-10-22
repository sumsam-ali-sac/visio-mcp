"""Dependency manifests (package.json, pyproject.toml, go.mod, ...): find them and read dependency names."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from ..lists import as_list
from ..model import RepoInfo
from ..text import read_text
from ..walk import FileEntry


MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "gemfile", "composer.json", "pipfile",
}

MANIFEST_EXT = {".csproj", ".fsproj", ".sln"}


def is_manifest(low: str, ext: str) -> bool:
    return low in MANIFEST_NAMES or ext in MANIFEST_EXT or (low.startswith("requirements") and ext == ".txt")


def _py_req(s: str) -> str | None:
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", s)
    return m.group(1).lower().replace("_", "-") if m else None


def parse_manifest(path: Path) -> list[str]:
    name = path.name.lower()
    text = read_text(path)
    deps: list[str] = []
    try:
        if name == "package.json":
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                v = data.get(key)
                if isinstance(v, dict):
                    deps += [str(k).lower() for k in v]
        elif name == "pyproject.toml":
            data = tomllib.loads(text)
            proj = data.get("project", {})
            for s in as_list(proj.get("dependencies")):
                if (n := _py_req(str(s))):
                    deps.append(n)
            for group in (proj.get("optional-dependencies") or {}).values():
                deps += [n for s in as_list(group) if (n := _py_req(str(s)))]
            for group in (data.get("dependency-groups") or {}).values():
                deps += [n for s in as_list(group) if isinstance(s, str) and (n := _py_req(s))]
            poetry = data.get("tool", {}).get("poetry", {})
            deps += [k.lower().replace("_", "-") for k in (poetry.get("dependencies") or {}) if k.lower() != "python"]
            for g in (poetry.get("group") or {}).values():
                deps += [k.lower().replace("_", "-") for k in (g.get("dependencies") or {})]
        elif name == "pipfile":
            data = tomllib.loads(text)
            for sec in ("packages", "dev-packages"):
                deps += [k.lower().replace("_", "-") for k in (data.get(sec) or {})]
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-", "git+", "http")):
                    if n := _py_req(line):
                        deps.append(n)
        elif name.endswith((".csproj", ".fsproj")):
            deps += [m.lower() for m in re.findall(r'PackageReference\s+Include="([^"]+)"', text, re.I)]
            if m := re.search(r'<Project\s+Sdk="([^"]+)"', text):
                deps.append("sdk:" + m.group(1).lower())
        elif name == "go.mod":
            deps += [m.lower() for m in re.findall(
                r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[^\s]+)\s+v[\w.\-+]+", text, re.M)]
        elif name == "pom.xml":
            for g, a in re.findall(r"<groupId>\s*([^<]+?)\s*</groupId>\s*<artifactId>\s*([^<]+?)\s*</artifactId>", text):
                deps += [f"{g}:{a}".lower(), a.lower(), g.lower()]
            if "spring-boot" in text:
                deps.append("spring-boot")
        elif name.startswith("build.gradle"):
            for g, a in re.findall(r"""["']([\w.\-]+):([\w.\-]+)(?::[^"']*)?["']""", text):
                deps += [f"{g}:{a}".lower(), a.lower()]
            if "org.springframework.boot" in text:
                deps.append("spring-boot")
            if "io.quarkus" in text:
                deps.append("io.quarkus")
        elif name == "cargo.toml":
            data = tomllib.loads(text)
            for sec in ("dependencies", "dev-dependencies"):
                deps += [k.lower() for k in (data.get(sec) or {})]
        elif name == "gemfile":
            deps += [m.lower() for m in re.findall(r"""^\s*gem\s+['"]([^'"]+)""", text, re.M)]
        elif name == "composer.json":
            data = json.loads(text)
            for key in ("require", "require-dev"):
                v = data.get(key)
                if isinstance(v, dict):
                    deps += [str(k).lower() for k in v]
    except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
        pass
    seen: set[str] = set()
    return [d for d in deps if not (d in seen or seen.add(d))]


def has(deps: set[str], names: tuple[str, ...]) -> bool:
    for d in deps:
        for n in names:
            if d == n or d.startswith((n + "/", n + ".", n + ":")):
                return True
    return False


def read_dependencies(root: Path, manifests: list[FileEntry], info: RepoInfo) -> set[str]:
    """Fill info.manifests / info.dependencies and return every dependency name found."""
    manifests.sort(key=lambda f: (f.depth, f.rel))
    info.manifests = [m.rel for m in manifests[:60]]
    deps: set[str] = set()
    for m in manifests[:30]:
        found = parse_manifest(root / m.rel)
        if found:
            info.dependencies[m.rel] = found[:80]
            deps.update(found)
    return deps
