"""Install, remove and report on icon packs."""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from contextlib import ExitStack
from pathlib import Path

from visio_mcp.icons import index, sources
from visio_mcp.icons.http import Progress
from visio_mcp.icons.pack import detect, select, write_pack
from visio_mcp.icons.paths import cache_dir, provider_dir
from visio_mcp.icons.providers import PROVIDER_NAMES, PROVIDERS


class IconInstallError(RuntimeError):
    """Nothing could be installed; `hint` tells the user how to do it by hand."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def status() -> dict[str, dict]:
    """Per provider: count, source, path, installed_at (None when not installed)."""
    out: dict[str, dict] = {}
    for p in PROVIDERS:
        idx = index.load_index(p)
        out[p] = {
            "count": len(idx["icons"]) if idx else 0,
            "source": idx.get("source") if idx else None,
            "path": str(provider_dir(p)),
            "installed_at": idx.get("installed_at") if idx else None,
        }
    return out


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
    # The ExitStack closes every zip opened during install before the temp folder is deleted;
    # leftover locks (antivirus, indexers) must not fail an install that already succeeded.
    with tempfile.TemporaryDirectory(prefix="visio-mcp-icons-", ignore_cleanup_errors=True) as td, \
            ExitStack() as opened:
        tmp = Path(td)
        sources.clear_wheel_cache()
        if source:
            try:
                entries, label = sources.entries_from(source, say, tmp, opened)
            except (OSError, zipfile.BadZipFile, ValueError) as e:
                raise IconInstallError(f"could not read icons from {source}: {e}", _manual_hint(wanted[0])) from e
            names = [n for n, _ in entries]
            wheel_layout = any(re.search(r"(?:^|/)resources/(azure|aws|gcp)/", n.lower()) for n in names)
            if len(wanted) > 1:
                detected = detect(names)
                wanted = [p for p in wanted if p in detected]
                if not wanted:
                    raise IconInstallError(f"could not tell which cloud the icons in {source} belong to",
                                           "Name it: visio-ai icons install azure|aws|gcp --from PATH")
            for p in wanted:
                say(f"Installing {PROVIDER_NAMES[p]} icons")
                picked = select(entries, p, wheel_layout)
                if picked:
                    results[p] = write_pack(p, picked, label)
                else:
                    errors.append(f"{p}: no icons found in {source}")
        else:
            for p in wanted:
                done = False
                for src in sources.vendor_urls(p) + ["pypi"]:
                    what = "the `diagrams` icon set (PyPI)" if src == "pypi" else "the official pack"
                    say(f"{PROVIDER_NAMES[p]}: trying {what}")
                    try:
                        entries, label = sources.entries_from(src, say, tmp, opened)
                        wheel_layout = src == "pypi"
                        picked = select(entries, p, wheel_layout)
                        if len(picked) < (1 if src == "pypi" else 15):  # a wrong or partial vendor zip
                            raise OSError(f"only {len(picked)} icons")
                        say(f"Installing {len(picked)} {PROVIDER_NAMES[p]} icons")
                        results[p] = write_pack(p, picked, label)
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
        d = provider_dir(p)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            index.forget(p)
            gone.append(p)
    if provider in (None, "", "all"):
        shutil.rmtree(cache_dir() / "_png", ignore_errors=True)
    return gone
