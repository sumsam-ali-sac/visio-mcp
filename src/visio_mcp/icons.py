"""Official cloud architecture icons (Azure, AWS, Google Cloud), downloaded once into a local cache.

Cloud kinds (azure-*, aws-*, gcp-*) draw with the vendor's real service icon when its pack is
installed; everything else keeps the clean geometric shapes. Icons are never bundled with the
package (vendor licensing): `visio-ai icons install` fetches them onto the user's machine.

Sources, tried in order for each provider:

1. the vendor's official pack (SVG): Azure Architecture Icons, the AWS Architecture Icons asset
   package, Google Cloud's icon zips. Vendor URLs move every few months, so their pages are
   scraped for the current zip link and a few known patterns are tried.
2. the MIT-licensed `diagrams` package wheel from PyPI (PNG icons for every provider).
3. a zip file, folder or URL the user names (`visio-ai icons install azure --from PATH`).

Layout of the cache (VISIO_MCP_ICONS overrides the location):

    <cache>/<provider>/index.json     {"source", "installed_at", "icons": {key: "files/<key>.svg"}}
    <cache>/<provider>/files/...      one icon per normalized service name
    <cache>/_png/...                  SVG icons rasterized for emitters that need a bitmap
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterator

from visio_mcp import catalog

__all__ = [
    "PROVIDERS", "cache_dir", "normalize", "install", "remove", "status", "installed", "find", "explain",
    "resolve_image", "png_for", "pngs_for", "missing_for", "IconInstallError",
]

PROVIDERS = ("azure", "aws", "gcp")
PROVIDER_NAMES = {"azure": "Azure", "aws": "AWS", "gcp": "Google Cloud"}
IMAGE_EXTS = (".svg", ".png")
MAX_ICON_BYTES = 2_000_000
MAX_DOWNLOAD_BYTES = 400_000_000
RASTER_PX = 256  # SVG icons are rasterized at this size for .vsdx bitmaps
INDEX = "index.json"
UA = "visio-mcp (https://github.com/; icon installer) Python-urllib"

Progress = Callable[[str], None]


class IconInstallError(RuntimeError):
    """Nothing could be installed; `hint` tells the user how to do it by hand."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


# --- cache location ---------------------------------------------------------------------------


def cache_dir() -> Path:
    """Where icon packs live: VISIO_MCP_ICONS, else the platform's user cache folder."""
    env = os.environ.get("VISIO_MCP_ICONS")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "visio-mcp" / "icons"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "visio-mcp" / "icons"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "visio-mcp" / "icons"


# --- names ------------------------------------------------------------------------------------

_PREFIXES = re.compile(
    r"^(?:\d+-icon-service-|icon-service-|arch-category-|arch-|res-|"
    r"aws-|amazon-|azure-|microsoft-|google-cloud-|google-|gcp-)+"
)
_SUFFIXES = re.compile(
    r"(?:-(?:(?:16|20|24|32|40|48|64|80|96|128|256|512)(?:x\d+|px)?|light|dark|color|colour|rgb|cmyk|"
    r"icon|logo|svg|png|bg|bw))+$"
)


def normalize(name: str) -> str:
    """Icon file name (or a kind slug) -> comparable key.

    '10029-icon-service-Function-Apps.svg' -> 'function-apps'
    'Arch_AWS-Lambda_64.svg' -> 'lambda',  'Arch_Amazon-DynamoDB_48@5x.png' -> 'dynamodb'
    'Cloud-Run-512-color-rgb.svg' -> 'cloud-run', 'cloud_run.svg' -> 'cloud-run'
    """
    stem = Path(name).name
    low = stem.lower()
    if low.endswith(IMAGE_EXTS):
        stem = stem[: -4]
    s = stem.lower()
    s = re.sub(r"@\d+x$", "", s)  # retina suffix
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    for _ in range(3):  # prefixes and suffixes can stack ('arch-amazon-x-64-light')
        s2 = _SUFFIXES.sub("", _PREFIXES.sub("", s)).strip("-")
        if s2 == s or not s2:
            break
        s = s2
    return s[:100]


def _squash(key: str) -> str:
    return key.replace("-", "")


def _tokens(key: str) -> set[str]:
    out = set()
    for t in key.split("-"):
        if not t:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


# Curated kind -> icon names, in priority order (normalized; both the official vendor packs'
# naming and the `diagrams` package's naming). find() falls back to fuzzy token overlap.
ICON_NAMES: dict[str, tuple[str, ...]] = {
    # Azure
    "azure-app-service": ("app-services", "app-service"),
    "azure-functions": ("function-apps", "functions", "function-app"),
    "azure-aks": ("kubernetes-services", "kubernetes-service", "aks"),
    "azure-container-apps": ("container-apps", "worker-container-app", "container-apps-environments"),
    "azure-vm": ("virtual-machine", "virtual-machines", "vm"),
    "azure-static-web-apps": ("static-apps", "static-web-apps"),
    "azure-logic-apps": ("logic-apps",),
    "azure-sql-database": ("sql-database", "sql-databases", "sql-db"),
    "azure-cosmos-db": ("cosmos-db", "cosmosdb"),
    "azure-redis": ("cache-redis", "cache-for-redis", "redis-cache", "redis"),
    "azure-storage-account": ("storage-accounts", "storage-account"),
    "azure-blob-storage": ("blob-storage", "storage-accounts", "blob-block"),
    "azure-ai-search": ("ai-search", "cognitive-search", "search-services", "search"),
    "azure-machine-learning": ("machine-learning", "machine-learning-studio-workspaces",
                               "machine-learning-service-workspaces"),
    "azure-private-endpoint": ("private-endpoints", "private-endpoint"),
    "azure-synapse": ("synapse-analytics", "synapse"),
    "azure-databricks": ("databricks",),
    "azure-data-factory": ("data-factories", "data-factory"),
    "azure-service-bus": ("service-bus",),
    "azure-event-hubs": ("event-hubs",),
    "azure-event-grid": ("event-grid-topics", "event-grid", "event-grid-domains"),
    "azure-api-management": ("api-management-services", "api-management"),
    "azure-front-door": ("front-door-and-cdn-profiles", "front-doors", "front-door"),
    "azure-application-gateway": ("application-gateways", "application-gateway"),
    "azure-load-balancer": ("load-balancers", "load-balancer"),
    "azure-vnet": ("virtual-networks", "virtual-network"),
    "azure-dns": ("dns-zones", "dns"),
    "azure-cdn": ("cdn-profiles", "cdn"),
    "azure-firewall": ("firewalls", "firewall"),
    "azure-bastion": ("bastions", "bastion"),
    "azure-key-vault": ("key-vaults", "key-vault"),
    "azure-entra-id": ("entra-id", "active-directory", "entra-id-protection"),
    "azure-monitor": ("monitor",),
    "azure-app-insights": ("application-insights",),
    "azure-log-analytics": ("log-analytics-workspaces", "log-analytics"),
    "azure-openai": ("openai", "azure-openai"),
    "azure-container-registry": ("container-registries", "container-registry"),
    # AWS
    "aws-ec2": ("ec2",),
    "aws-lambda": ("lambda",),
    "aws-ecs": ("elastic-container-service", "ecs"),
    "aws-eks": ("elastic-kubernetes-service", "eks"),
    "aws-fargate": ("fargate",),
    "aws-s3": ("simple-storage-service", "simple-storage-service-s3", "s3"),
    "aws-rds": ("rds",),
    "aws-aurora": ("aurora",),
    "aws-dynamodb": ("dynamodb",),
    "aws-elasticache": ("elasticache",),
    "aws-redshift": ("redshift",),
    "aws-athena": ("athena",),
    "aws-glue": ("glue",),
    "aws-kinesis": ("kinesis", "kinesis-data-streams"),
    "aws-sqs": ("simple-queue-service", "simple-queue-service-sqs", "sqs"),
    "aws-sns": ("simple-notification-service", "simple-notification-service-sns", "sns"),
    "aws-eventbridge": ("eventbridge",),
    "aws-step-functions": ("step-functions",),
    "aws-api-gateway": ("api-gateway",),
    "aws-cloudfront": ("cloudfront",),
    "aws-route53": ("route-53", "route53"),
    "aws-alb": ("elastic-load-balancing", "elb-application-load-balancer", "elastic-load-balancing-application-load-balancer"),
    "aws-vpc": ("virtual-private-cloud", "vpc"),
    "aws-waf": ("waf",),
    "aws-nat-gateway": ("vpc-nat-gateway", "nat-gateway"),
    "aws-opensearch": ("opensearch-service", "elasticsearch-service", "opensearch"),
    "aws-iam": ("identity-and-access-management", "identity-and-access-management-iam", "iam"),
    "aws-cognito": ("cognito",),
    "aws-kms": ("key-management-service", "kms"),
    "aws-secrets-manager": ("secrets-manager",),
    "aws-cloudwatch": ("cloudwatch",),
    "aws-sagemaker": ("sagemaker-ai", "sagemaker"),
    "aws-bedrock": ("bedrock",),
    "aws-ecr": ("elastic-container-registry", "ec2-container-registry", "ecr"),
    # Google Cloud ('google-' and 'gcp-' are stripped by normalize)
    "gcp-compute-engine": ("compute-engine",),
    "gcp-cloud-run": ("cloud-run", "run"),
    "gcp-gke": ("kubernetes-engine", "gke"),
    "gcp-cloud-functions": ("cloud-functions", "functions"),
    "gcp-app-engine": ("app-engine",),
    "gcp-cloud-storage": ("cloud-storage", "storage"),
    "gcp-cloud-sql": ("cloud-sql", "sql"),
    "gcp-spanner": ("cloud-spanner", "spanner"),
    "gcp-firestore": ("firestore", "cloud-firestore"),
    "gcp-bigtable": ("cloud-bigtable", "bigtable"),
    "gcp-bigquery": ("bigquery",),
    "gcp-memorystore": ("memorystore", "cloud-memorystore"),
    "gcp-artifact-registry": ("artifact-registry", "container-registry"),
    "gcp-pubsub": ("pubsub", "pub-sub", "cloud-pubsub"),
    "gcp-eventarc": ("eventarc", "pubsub"),
    "gcp-alloydb": ("alloydb", "alloy-db", "cloud-sql", "sql"),
    "gcp-looker": ("looker",),
    "gcp-dataflow": ("dataflow", "cloud-dataflow"),
    "gcp-dataproc": ("dataproc", "cloud-dataproc"),
    "gcp-api-gateway": ("api-gateway", "cloud-api-gateway", "apigee"),
    "gcp-cloud-load-balancing": ("cloud-load-balancing", "load-balancing"),
    "gcp-cloud-cdn": ("cloud-cdn", "cdn"),
    "gcp-cloud-dns": ("cloud-dns", "dns"),
    "gcp-vpc": ("virtual-private-cloud", "vpc"),
    "gcp-iam": ("identity-and-access-management", "cloud-iam", "iam"),
    "gcp-secret-manager": ("secret-manager",),
    "gcp-cloud-armor": ("cloud-armor", "armor"),
    "gcp-cloud-monitoring": ("cloud-monitoring", "monitoring"),
    "gcp-cloud-logging": ("cloud-logging", "logging"),
    "gcp-vertex-ai": ("vertex-ai",),
    "gcp-cloud-build": ("cloud-build", "build"),
    "gcp-cloud-scheduler": ("cloud-scheduler", "scheduler"),
}

# Icons drawn for a kind that are a stand-in rather than the service itself (no official icon
# for it in the `diagrams` pack); reported so users know.
STAND_INS = {"gcp-eventarc", "gcp-alloydb"}


# --- index ------------------------------------------------------------------------------------

_index_cache: dict[Path, tuple[float, dict]] = {}


def _provider_dir(provider: str) -> Path:
    return cache_dir() / provider


def _load_index(provider: str) -> dict | None:
    p = _provider_dir(provider) / INDEX
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    hit = _index_cache.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data.get("icons"), dict):
            return None
    except (OSError, ValueError, AttributeError):
        return None
    data["_squashed"] = {}
    for k in data["icons"]:
        data["_squashed"].setdefault(_squash(k), k)
    _index_cache[p] = (mtime, data)
    return data


def installed(provider: str) -> bool:
    idx = _load_index(provider)
    return bool(idx and idx["icons"])


def status() -> dict[str, dict]:
    """Per provider: count, source, path, installed_at (None when not installed)."""
    out: dict[str, dict] = {}
    for p in PROVIDERS:
        idx = _load_index(p)
        out[p] = {
            "count": len(idx["icons"]) if idx else 0,
            "source": idx.get("source") if idx else None,
            "path": str(_provider_dir(p)),
            "installed_at": idx.get("installed_at") if idx else None,
        }
    return out


def missing_for(kind_names: list[str] | tuple[str, ...]) -> list[str]:
    """Providers used by these kinds whose icon pack is not installed (catalog order)."""
    used = []
    for name in kind_names:
        k = catalog.lookup(name)
        if k and k.provider and k.provider not in used:
            used.append(k.provider)
    return [p for p in PROVIDERS if p in used and not installed(p)]


# --- lookup -----------------------------------------------------------------------------------


def _match(idx: dict, name: str) -> str | None:
    key = normalize(name)
    if key in idx["icons"]:
        return key
    return idx["_squashed"].get(_squash(key))


def _fuzzy(idx: dict, words: set[str]) -> str | None:
    best, best_score = None, 0.0
    for key in idx["icons"]:
        t = _tokens(key)
        inter = len(words & t)
        if not inter:
            continue
        score = inter / max(len(words), len(t))
        if score > best_score or (score == best_score and best is not None and len(key) < len(best)):
            best, best_score = key, score
    return best if best_score >= 0.5 else None


def explain(kind_name: str) -> tuple[str | None, str | None, str]:
    """(provider, matched icon key, how) where how is 'curated' | 'fuzzy' | 'none' | 'no-pack'."""
    k = catalog.lookup(kind_name)
    if k is None or not k.provider:
        return None, None, "none"
    idx = _load_index(k.provider)
    if not idx:
        return k.provider, None, "no-pack"
    slug = k.name[len(k.provider) + 1:]
    for cand in ICON_NAMES.get(k.name, ()) + (slug,):
        hit = _match(idx, cand)
        if hit:
            return k.provider, hit, "curated"
    hit = _fuzzy(idx, _tokens(normalize(slug)))
    return k.provider, hit, "fuzzy" if hit else "none"


def find(kind_name: str) -> Path | None:
    """The installed official icon for a cloud kind (None for generic kinds or no pack)."""
    k = catalog.lookup(kind_name)
    if k is None or not k.provider:
        return None
    _, key, _ = explain(k.name)
    if not key:
        return None
    idx = _load_index(k.provider)
    assert idx is not None
    p = _provider_dir(k.provider) / idx["icons"][key]
    return p if p.is_file() else None


def resolve_image(node_icon: str | None, kind_name: str) -> Path | None:
    """A custom Node.icon (existing .svg/.png) wins; else the kind's official icon, if installed."""
    if node_icon:
        p = Path(node_icon).expanduser()
        if p.suffix.lower() in IMAGE_EXTS and p.is_file():
            return p.resolve()
        return None
    return find(kind_name)


# --- install ----------------------------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.isfile(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def _open(url: str, timeout: float = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def _fetch_text(url: str, timeout: float = 20) -> str:
    with _open(url, timeout) as r:
        return r.read(8_000_000).decode("utf-8", "replace")


def _download(url: str, dest: Path, say: Progress) -> Path:
    with _open(url, 60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_DOWNLOAD_BYTES:
                raise OSError("download too large")
            f.write(chunk)
            now = time.monotonic()
            if now - last > 0.25:
                last = now
                pct = f" {done * 100 // total}%" if total else ""
                say(f"Downloading {Path(url.split('?')[0]).name}{pct} ({done >> 20} MB)")
    return dest


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
        html = _fetch_text(page_url)
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
        if link.lower().split("?")[0].endswith(".zip") and re.search(pattern, link, re.I) and link not in out:
            out.append(link)
    return out


def _vendor_urls(provider: str) -> list[str]:
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


def _pypi_wheel(say: Progress, tmp: Path) -> Path:
    cached = _PYPI_WHEEL.get("diagrams")
    if cached and cached.is_file():
        return cached
    say("Looking up the `diagrams` icon set on PyPI")
    meta = json.loads(_fetch_text("https://pypi.org/pypi/diagrams/json"))
    wheels = [u for u in meta.get("urls", []) if u.get("packagetype") == "bdist_wheel"]
    if not wheels:
        raise OSError("no wheel for `diagrams` on PyPI")
    url = wheels[0]["url"]
    dest = tmp / Path(url).name
    _download(url, dest, say)
    _PYPI_WHEEL["diagrams"] = dest
    return dest


# entries -----------------------------------------------------------------------------------------

Entry = tuple[str, Callable[[], bytes]]  # (path inside the source, reader)


def _zip_entries(z: zipfile.ZipFile, prefix: str = "", depth: int = 0) -> Iterator[Entry]:
    for info in z.infolist():
        name = info.filename
        if info.is_dir() or "__MACOSX" in name or Path(name).name.startswith("."):
            continue
        low = name.lower()
        if low.endswith(".zip") and depth < 2 and info.file_size < MAX_DOWNLOAD_BYTES:
            try:
                inner = zipfile.ZipFile(io.BytesIO(z.read(info)))
            except (zipfile.BadZipFile, OSError):
                continue
            yield from _zip_entries(inner, prefix + name + "/", depth + 1)
        elif low.endswith(IMAGE_EXTS) and info.file_size <= MAX_ICON_BYTES:
            yield prefix + name, (lambda z=z, info=info: z.read(info))


def _dir_entries(root: Path) -> Iterator[Entry]:
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "__MACOSX" in p.parts or p.name.startswith("."):
            continue
        low = p.name.lower()
        if low.endswith(".zip"):
            try:
                with zipfile.ZipFile(p) as z:
                    for name, read in _zip_entries(z, p.relative_to(root).as_posix() + "/", 1):
                        data = read()
                        yield name, (lambda d=data: d)
            except (zipfile.BadZipFile, OSError):
                continue
        elif low.endswith(IMAGE_EXTS) and p.stat().st_size <= MAX_ICON_BYTES:
            yield p.relative_to(root).as_posix(), (lambda p=p: p.read_bytes())


def _detect(names: list[str]) -> set[str]:
    """Which providers a source holds icons for, from its file names."""
    found: set[str] = set()
    for n in names:
        low = n.lower()
        m = re.search(r"(?:^|/)resources/(azure|aws|gcp)/", low)
        if m:
            found.add(m.group(1))
        elif "icon-service-" in low or "azure" in low:
            found.add("azure")
        elif re.search(r"(?:^|/)(arch|res)_", low) or "aws" in low or "amazon" in low:
            found.add("aws")
        elif "google" in low or "gcp" in low or "cloud_" in low or "cloud-" in low:
            found.add("gcp")
    return found


def _score(path: str) -> tuple:
    """Higher wins when two files normalize to the same key."""
    low = path.lower()
    size = 0
    m = re.search(r"[_-](\d{2,3})(?:@\dx)?(?:[_-](?:light|dark))?\.(?:svg|png)$", low)
    if m:
        size = int(m.group(1))
    return (
        low.endswith(".svg"),  # vector beats bitmap
        "dark" not in Path(low).name,  # light variants for light pages
        "/res_" not in low and not Path(low).name.startswith("res_"),  # service icon over resource icon
        "legacy" not in low,
        size,
        -low.count("/"),
    )


def _select(entries: list[Entry], provider: str, wheel_layout: bool) -> dict[str, Entry]:
    chosen: dict[str, tuple[tuple, Entry]] = {}
    aliases: dict[str, tuple[tuple, Entry]] = {}
    for name, read in entries:
        low = name.lower()
        if wheel_layout:
            m = re.search(r"(?:^|/)resources/([a-z0-9]+)/", low)
            if not m or m.group(1) != provider:
                continue
        if "arch-category" in low or "arch_category" in low or "/category" in low:
            continue  # category tiles, not services
        key = normalize(name)
        if not key or not re.fullmatch(r"[a-z0-9-]+", key):
            continue
        score = _score(name)
        if key not in chosen or score > chosen[key][0]:
            chosen[key] = (score, (name, read))
        if provider == "gcp" and not wheel_layout:  # Google packs often name the folder after the product
            parent = normalize(Path(name).parent.name)
            if parent and parent not in ("svg", "png", "icons", "") and re.fullmatch(r"[a-z0-9-]+", parent):
                if parent not in aliases or score > aliases[parent][0]:
                    aliases[parent] = (score, (name, read))
    for key, val in aliases.items():
        chosen.setdefault(key, val)
    return {k: v[1] for k, v in chosen.items()}


def _write_pack(provider: str, picked: dict[str, Entry], source: str) -> int:
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{provider}-", dir=root))
    try:
        files = tmp / "files"
        files.mkdir()
        icons: dict[str, str] = {}
        for key, (name, read) in sorted(picked.items()):
            ext = Path(name).suffix.lower()
            data = read()
            if ext == ".svg" and b"<svg" not in data[:4096].lower() and b"<svg" not in data.lower():
                continue
            if ext == ".png" and not data.startswith(b"\x89PNG"):
                continue
            (files / f"{key}{ext}").write_bytes(data)
            icons[key] = f"files/{key}{ext}"
        if not icons:
            raise OSError("no usable icons")
        meta = {"provider": provider, "source": source, "count": len(icons),
                "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "icons": icons}
        (tmp / INDEX).write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")
        dest = _provider_dir(provider)
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
        _index_cache.pop(dest / INDEX, None)
        return len(icons)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _entries_from(source: str, say: Progress, tmp: Path) -> tuple[list[Entry], str]:
    """Open a URL / zip / folder (or 'pypi') and list its image entries. Returns (entries, label)."""
    if source == "pypi":
        wheel = _pypi_wheel(say, tmp)
        z = zipfile.ZipFile(wheel)
        return list(_zip_entries(z)), "pypi:diagrams (" + wheel.name + ")"
    if re.match(r"^https?://", source, re.I):
        say(f"Downloading {Path(source.split('?')[0]).name}")
        dest = tmp / (hashlib.sha1(source.encode()).hexdigest()[:12] + ".zip")
        if not dest.exists():
            _download(source, dest, say)
        z = zipfile.ZipFile(dest)
        return list(_zip_entries(z)), source
    p = Path(source).expanduser()
    if p.is_dir():
        return list(_dir_entries(p)), str(p.resolve())
    if p.is_file():
        if p.suffix.lower() in IMAGE_EXTS:
            return [(p.name, lambda p=p: p.read_bytes())], str(p.resolve())
        z = zipfile.ZipFile(p)
        return list(_zip_entries(z)), str(p.resolve())
    raise FileNotFoundError(f"no such file or folder: {source}")


def _manual_hint(provider: str | None) -> str:
    pages = {"azure": "https://learn.microsoft.com/azure/architecture/icons/",
             "aws": "https://aws.amazon.com/architecture/icons/",
             "gcp": "https://cloud.google.com/icons"}
    p = provider or "azure"
    return (f"Download the official icon zip ({pages.get(p, pages['azure'])}) and run: "
            f"visio-ai icons install {p} --from PATH_TO_ZIP")


def install(provider: str | None = None, source: str | None = None,
            progress: Progress | None = None) -> dict[str, int]:
    """Install icon packs into the cache. Returns {provider: icon count} for what was installed.

    provider: 'azure' | 'aws' | 'gcp' | None/'all'. source: a URL, zip file or folder; default
    tries the vendor's official pack, then the `diagrams` wheel from PyPI.
    """
    say = progress or (lambda _m: None)
    if provider in (None, "", "all"):
        wanted = list(PROVIDERS)
    else:
        p = provider.strip().lower()
        p = {"google": "gcp", "gcloud": "gcp", "amazon": "aws", "microsoft": "azure"}.get(p, p)
        if p not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r}; use one of: {', '.join(PROVIDERS)}, all")
        wanted = [p]
    results: dict[str, int] = {}
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="visio-mcp-icons-") as td:
        tmp = Path(td)
        _PYPI_WHEEL.clear()
        if source:
            try:
                entries, label = _entries_from(source, say, tmp)
            except (OSError, zipfile.BadZipFile, ValueError) as e:
                raise IconInstallError(f"could not read icons from {source}: {e}", _manual_hint(wanted[0])) from e
            names = [n for n, _ in entries]
            wheel_layout = any(re.search(r"(?:^|/)resources/(azure|aws|gcp)/", n.lower()) for n in names)
            if len(wanted) > 1:
                detected = _detect(names)
                wanted = [p for p in wanted if p in detected]
                if not wanted:
                    raise IconInstallError(f"could not tell which cloud the icons in {source} belong to",
                                           "Name it: visio-ai icons install azure|aws|gcp --from PATH")
            for p in wanted:
                say(f"Installing {PROVIDER_NAMES[p]} icons")
                picked = _select(entries, p, wheel_layout)
                if picked:
                    results[p] = _write_pack(p, picked, label)
                else:
                    errors.append(f"{p}: no icons found in {source}")
        else:
            for p in wanted:
                done = False
                for src in _vendor_urls(p) + ["pypi"]:
                    what = "the `diagrams` icon set (PyPI)" if src == "pypi" else "the official pack"
                    say(f"{PROVIDER_NAMES[p]}: trying {what}")
                    try:
                        entries, label = _entries_from(src, say, tmp)
                        wheel_layout = src == "pypi"
                        picked = _select(entries, p, wheel_layout)
                        if len(picked) < 15:  # a wrong or partial zip
                            raise OSError(f"only {len(picked)} icons")
                        say(f"Installing {len(picked)} {PROVIDER_NAMES[p]} icons")
                        results[p] = _write_pack(p, picked, label)
                        done = True
                        break
                    except Exception as e:  # network, proxy, moved URLs, bad zips: try the next
                        errors.append(f"{p}: {src}: {type(e).__name__}: {e}")
                        continue
                if not done:
                    errors.append(f"{p}: no source worked")
    if not results:
        detail = "; ".join(errors[-3:])
        raise IconInstallError(f"could not install cloud icons ({detail})", _manual_hint(wanted[0] if wanted else None))
    return results


def remove(provider: str | None = None) -> list[str]:
    """Delete installed packs (all when provider is None/'all'). Returns the providers removed."""
    wanted = list(PROVIDERS) if provider in (None, "", "all") else [provider.strip().lower()]
    gone = []
    for p in wanted:
        d = _provider_dir(p)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            _index_cache.pop(d / INDEX, None)
            gone.append(p)
    if provider in (None, "", "all"):
        shutil.rmtree(cache_dir() / "_png", ignore_errors=True)
    return gone


# --- rasterizing ------------------------------------------------------------------------------


def _png_target(svg: Path) -> Path:
    st = svg.stat()
    h = hashlib.sha1(f"{svg.resolve()}|{st.st_mtime_ns}|{st.st_size}|{RASTER_PX}".encode()).hexdigest()[:16]
    return cache_dir() / "_png" / f"{normalize(svg.name) or 'icon'}-{h}.png"


def _raster_playwright(jobs: list[tuple[Path, Path]]) -> None:
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    from visio_mcp.svg import _find_chromium

    args = ["--no-sandbox", "--disable-gpu"]
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=args)
        except Exception:
            exe = _find_chromium()
            if not exe:
                raise
            browser = pw.chromium.launch(executable_path=exe, args=args)
        try:
            page = browser.new_page(viewport={"width": RASTER_PX, "height": RASTER_PX})
            for src, dest in jobs:
                uri = "data:image/svg+xml;base64," + base64.b64encode(src.read_bytes()).decode()
                page.set_content(
                    "<!doctype html><style>html,body{margin:0;background:transparent}"
                    f"img{{display:block;width:{RASTER_PX}px;height:{RASTER_PX}px;object-fit:contain}}</style>"
                    f'<img src="{uri}">')
                page.wait_for_function("document.images[0].complete")
                dest.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(dest), omit_background=True,
                                clip={"x": 0, "y": 0, "width": RASTER_PX, "height": RASTER_PX})
        finally:
            browser.close()


def _raster_cairosvg(jobs: list[tuple[Path, Path]]) -> None:
    import cairosvg  # type: ignore[import-not-found]

    for src, dest in jobs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(src), write_to=str(dest), output_width=RASTER_PX, output_height=RASTER_PX)


def pngs_for(paths: list[Path]) -> dict[Path, Path | None]:
    """Bitmaps for icons (PNG as-is, SVG rasterized once into the cache). None where impossible."""
    out: dict[Path, Path | None] = {}
    jobs: list[tuple[Path, Path]] = []
    for p in dict.fromkeys(Path(x) for x in paths):
        if p.suffix.lower() == ".png":
            out[p] = p
            continue
        try:
            dest = _png_target(p)
        except OSError:
            out[p] = None
            continue
        out[p] = dest
        if not dest.is_file():
            jobs.append((p, dest))
    if jobs:
        for fn in (_raster_playwright, _raster_cairosvg):
            try:
                fn(jobs)
                break
            except Exception:
                continue
        for src, dest in jobs:
            if not dest.is_file():
                out[src] = None
    return out


def png_for(path: str | os.PathLike) -> Path | None:
    """A PNG for one icon; SVGs are rasterized via playwright/chromium or cairosvg."""
    return pngs_for([Path(path)])[Path(path)]
