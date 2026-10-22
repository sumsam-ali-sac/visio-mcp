"""Tolerant parser for the common YAML subset found in CI, compose, k8s and IaC files."""

from __future__ import annotations

import json
import re
from typing import Any


_BLOCK_RE = re.compile(r"(?:^|:\s+|^-\s+)[|>][+-]?\d*$")
_KEY_RE = re.compile(r"""^(?P<k>"[^"]*"|'[^']*'|[^:\s'"\[\{#-][^:]*?|-[^:\s][^:]*?)\s*:(?:\s+(?P<v>.*))?$""")


def _strip_comment(s: str) -> str:
    q: str | None = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            if i == 0 or s[i - 1] in " :[{,-":
                q = ch
        elif ch == "#" and (i == 0 or s[i - 1] == " "):
            return s[:i].rstrip()
    return s


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    raw = text.expandtabs(2).splitlines()
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        i += 1
        s = line.strip()
        if not s or s.startswith(("#", "%")) or s in ("---", "..."):
            continue
        ind = len(line) - len(line.lstrip(" "))
        content = _strip_comment(s)
        m = _BLOCK_RE.search(content)
        if m:
            block: list[str] = []
            while i < len(raw):
                nxt = raw[i]
                if not nxt.strip():
                    i += 1
                    continue
                if len(nxt) - len(nxt.lstrip(" ")) <= ind:
                    break
                block.append(nxt.strip())
                i += 1
            pre = re.match(r"(:\s+|-\s+)?", m.group(0)).group(0)  # type: ignore[union-attr]
            content = content[: m.start()] + pre + json.dumps(" ".join(block)[:600])
        out.append((ind, content))
    return out


def _split_flow(s: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    q: str | None = None
    cur: list[str] = []
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _scalar(v: str) -> Any:
    v = v.strip()
    if v in ("", "~", "null"):
        return None
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        if v[0] == '"':
            try:
                return json.loads(v)
            except ValueError:
                pass
        return v[1:-1]
    if v[0] == "[" and v[-1] == "]":
        inner = v[1:-1].strip()
        return [_scalar(x) for x in _split_flow(inner)] if inner else []
    if v[0] == "{" and v[-1] == "}":
        d: dict[str, Any] = {}
        for part in _split_flow(v[1:-1]):
            k, sep, val = part.partition(":")
            if sep:
                d[k.strip().strip("\"'")] = _scalar(val)
        return d
    return v


def _is_kv(s: str) -> bool:
    return _KEY_RE.match(s) is not None


def _parse(lines: list[tuple[int, str]], i: int) -> tuple[Any, int]:
    ind, content = lines[i]
    if content.startswith("- ") or content == "-":
        return _parse_list(lines, i, ind)
    return _parse_map(lines, i, ind)


def _parse_list(lines: list[tuple[int, str]], i: int, ind: int) -> tuple[list[Any], int]:
    res: list[Any] = []
    while i < len(lines) and lines[i][0] == ind and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        content = lines[i][1]
        rest = content[1:].lstrip()
        if not rest:
            i += 1
            if i < len(lines) and lines[i][0] > ind:
                v, i = _parse(lines, i)
                res.append(v)
            else:
                res.append(None)
        elif _is_kv(rest):
            offset = len(content) - len(rest)
            lines[i] = (ind + offset, rest)
            v, i = _parse_map(lines, i, ind + offset)
            res.append(v)
        elif rest.startswith("- "):
            offset = len(content) - len(rest)
            lines[i] = (ind + offset, rest)
            v, i = _parse_list(lines, i, ind + offset)
            res.append(v)
        else:
            res.append(_scalar(rest))
            i += 1
    return res, i


def _parse_map(lines: list[tuple[int, str]], i: int, ind: int) -> tuple[dict[str, Any], int]:
    res: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] >= ind:
        lind, content = lines[i]
        if lind > ind or content.startswith("- "):
            if content.startswith("- ") and lind == ind:
                break
            i += 1
            continue
        m = _KEY_RE.match(content)
        i += 1
        if not m:
            continue
        key = m.group("k").strip().strip("\"'")
        rest = (m.group("v") or "").strip()
        if not rest:
            if i < len(lines) and (
                lines[i][0] > ind or (lines[i][0] == ind and lines[i][1].startswith("- "))
            ):
                v, i = _parse(lines, i)
            else:
                v = None
        else:
            v = _scalar(rest)
        res[key] = v
    return res, i


def parse_yaml(text: str) -> Any:
    """Parse the common subset of YAML (maps, lists, scalars, flow collections, block scalars).

    Tolerant: returns {} on anything it cannot make sense of.
    """
    try:
        lines = _yaml_lines(text)
        if not lines:
            return {}
        v, _ = _parse(lines, 0)
        return v
    except Exception:  # noqa: BLE001 - tolerant by design
        return {}


def yaml_docs(text: str) -> list[Any]:
    docs = re.split(r"^---[ \t]*$", text, flags=re.M)
    return [d for d in (parse_yaml(p) for p in docs if p.strip()) if d]
