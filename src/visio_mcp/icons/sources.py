"""Where icon packs come from: vendor pages scraped for zip links, and the `diagrams` wheel on PyPI."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from visio_mcp.icons.http import Progress, download, fetch_text
from visio_mcp.icons.pack import Entry, dir_entries, zip_entries
from visio_mcp.icons.providers import IMAGE_EXTS


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        for k, v in attrs:
            if k == "href" and v:
                self.links.append(v)


def _zip_links(page_url: str, pattern: str) -> list[str]:
    try:
        html = fetch_text(page_url)
    except Exception:
        return []
    p = _Links()
    try:
        p.feed(html)
    except Exception:
        pass
    found = p.links + re.findall(r"https?://[^\s\"'<>]+?\.zip", html)
    out = []
    for link in found:
        link = urllib.request.urljoin(page_url, link.replace("&amp;", "&"))
        if link.lower().split("?")[0].endswith(".zip") and re.search(pattern, link, re.IGNORECASE) and link not in out:
            out.append(link)
    return out


def vendor_urls(provider: str) -> list[str]:
    """Current official pack URLs (scraped from the vendor's icon page, then known patterns)."""
    if provider == "azure":
        urls = _zip_links("https://learn.microsoft.com/en-us/azure/architecture/icons/", r"icon")
        urls += [f"https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V{n}.zip"
                 for n in range(24, 16, -1)]
        return list(dict.fromkeys(urls))
    if provider == "aws":
        return _zip_links("https://aws.amazon.com/architecture/icons/", r"asset[-_]?package")
    if provider == "gcp":
        urls = _zip_links("https://cloud.google.com/icons", r"icons")
        urls += ["https://services.google.com/fh/files/misc/core-products-icons.zip",
                 "https://services.google.com/fh/files/misc/google-cloud-legacy-icons.zip"]
        urls = list(dict.fromkeys(u for u in urls if "category" not in u.lower()))
        # current product icons first; the legacy pack fills in products without a new icon
        return sorted(urls, key=lambda u: "legacy" in u.lower())
    return []


_PYPI_WHEEL: dict[str, Path] = {}  # one download per process (installing 'all' reuses it)


def pypi_wheel(say: Progress, tmp: Path) -> Path:
    cached = _PYPI_WHEEL.get("diagrams")
    if cached and cached.is_file():
        return cached
    say("Looking up the `diagrams` icon set on PyPI")
    meta = json.loads(fetch_text("https://pypi.org/pypi/diagrams/json"))
    wheels = [u for u in meta.get("urls", []) if u.get("packagetype") == "bdist_wheel"]
    if not wheels:
        raise OSError("no wheel for `diagrams` on PyPI")
    url = wheels[0]["url"]
    dest = tmp / Path(url).name
    download(url, dest, say)
    _PYPI_WHEEL["diagrams"] = dest
    return dest


def entries_from(source: str, say: Progress, tmp: Path) -> tuple[list[Entry], str]:
    """Open a URL / zip / folder (or 'pypi') and list its image entries. Returns (entries, label)."""
    if source == "pypi":
        wheel = pypi_wheel(say, tmp)
        z = zipfile.ZipFile(wheel)
        return list(zip_entries(z)), "pypi:diagrams (" + wheel.name + ")"
    if re.match(r"^https?://", source, re.IGNORECASE):
        say(f"Downloading {Path(source.split('?')[0]).name}")
        dest = tmp / (hashlib.sha1(source.encode()).hexdigest()[:12] + ".zip")
        if not dest.exists():
            download(source, dest, say)
        z = zipfile.ZipFile(dest)
        return list(zip_entries(z)), source
    p = Path(source).expanduser()
    if p.is_dir():
        return list(dir_entries(p)), str(p.resolve())
    if p.is_file():
        if p.suffix.lower() in IMAGE_EXTS:
            return [(p.name, lambda p=p: p.read_bytes())], str(p.resolve())
        z = zipfile.ZipFile(p)
        return list(zip_entries(z)), str(p.resolve())
    raise FileNotFoundError(f"no such file or folder: {source}")


def clear_wheel_cache() -> None:
    _PYPI_WHEEL.clear()
