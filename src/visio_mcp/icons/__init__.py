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

Modules:

providers  PROVIDERS, display names, accepted image extensions
paths      cache location (cache_dir) and per-provider folders
names      normalize() and the curated kind -> icon name table
index      cached reader for a pack's index.json
http       downloads with a size cap and progress messages
sources    vendor page scraping, the PyPI `diagrams` wheel, opening a URL/zip/folder
pack       selecting icons from a source and writing a pack
install    install, remove, status, IconInstallError
lookup     installed, missing_for, find, explain, resolve_image
raster     png_for, pngs_for
"""

from visio_mcp.icons.install import IconInstallError, install, remove, status
from visio_mcp.icons.lookup import explain, find, installed, missing_for, resolve_image
from visio_mcp.icons.names import ICON_NAMES, STAND_INS, normalize
from visio_mcp.icons.paths import cache_dir
from visio_mcp.icons.providers import PROVIDER_NAMES, PROVIDERS
from visio_mcp.icons.raster import png_for, pngs_for

__all__ = [
    "ICON_NAMES", "PROVIDERS", "PROVIDER_NAMES", "STAND_INS", "IconInstallError", "cache_dir", "explain", "find",
    "install", "installed", "missing_for", "normalize", "png_for", "pngs_for", "remove", "resolve_image",
    "status",
]
