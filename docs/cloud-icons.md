# Cloud architecture icons

Cloud diagrams look right only with the official service icons. visio-mcp uses them for every
`azure-*`, `aws-*` and `gcp-*` kind, in all three outputs: live Visio, the native `.vsdx`, and
SVG/HTML/PNG previews.

## Install

```powershell
visio-ai icons install            # Azure, AWS and Google Cloud
visio-ai icons install azure      # just one
visio-ai icons                    # status: what's installed, from where
visio-ai icons remove aws
```

From an MCP client: `install_icons(provider="all")`.

Sources, in order:

1. **The official packs** published by Microsoft
   ([Azure Architecture Icons](https://learn.microsoft.com/azure/architecture/icons/)), AWS
   ([AWS Architecture Icons](https://aws.amazon.com/architecture/icons/)) and Google
   ([Google Cloud icons](https://cloud.google.com/icons)) — SVG, best quality.
2. **Fallback:** the icons bundled with the MIT-licensed
   [`diagrams`](https://pypi.org/project/diagrams/) package on PyPI (PNG), when the vendor
   download isn't reachable (proxies, firewalls).

Behind a strict proxy, download the pack yourself and point at the zip or folder:

```powershell
visio-ai icons install azure --from C:\Downloads\Azure_Public_Service_Icons.zip
```

Icons are stored in your user cache (`%LOCALAPPDATA%\visio-mcp\icons`, `~/Library/Caches/visio-mcp/icons`
or `~/.cache/visio-mcp/icons`; override with `VISIO_MCP_ICONS`). They are not part of this
repository: each vendor's icons are subject to that vendor's terms, which allow using them in
architecture diagrams.

## How icons are chosen

Each cloud kind has a curated list of icon names for each source's naming scheme
(`azure-functions` → *Function Apps*, `aws-lambda` → *AWS Lambda*, `gcp-cloud-run` → *Cloud Run*),
with fuzzy matching as a safety net. In order:

1. A node's own `icon` (path to an `.svg`/`.png`) always wins.
2. In Visio, a real Visio icon master for the service, when your Visio has that stencil.
3. The installed official icon (imported into Visio, embedded in the `.vsdx`, inlined in SVG).
4. Without icons: the base shape (e.g. `aws-rds` → database cylinder) in the provider's colors,
   or a colored tile with a short glyph in previews. The render result reminds you to install icons.

The label (and `[technology]`) sits under the icon, in the page's text color.

## Custom icons

Any node can use your own icon:

```json
{"id": "erp", "label": "SAP ERP", "kind": "external-system", "icon": "C:/icons/sap.svg"}
```
