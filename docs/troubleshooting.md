# Troubleshooting

Start with `visio-ai doctor`: it checks Visio, the AI provider, icon packs and preview renderers,
and prints the fix for anything missing.

## Visio

**"Visio desktop not found" on Windows.** visio-mcp looks for the `Visio.Application` COM
registration. Visio for the web and the Visio viewer don't provide it; you need Visio Professional
or Plan 2 desktop. Until then, `.vsdx` files are written natively and open in Visio for the web.

**"Call was rejected by callee" / Visio busy.** Visio is showing a dialog or is still starting.
Close dialogs and retry; startup is retried automatically for a few seconds.

**The diagram appears in a hidden Visio or not at all.** Live mode is the default; check that
`VISIO_MCP_HEADLESS` isn't set and that you didn't pass `--no-live`.

**Shapes are plain rectangles with a warning.** That kind's stencil isn't installed in your Visio
edition. Pick another kind (the warning suggests one), install the cloud icon packs for cloud
kinds, or check with `list_stencils` / `list_masters`.

**"…vsdx is open in another program; saved as …-2.vsdx".** The file was open in Visio; a free
name was used instead of overwriting.

## Previews without Visio

**No PNG.** PNGs need Playwright (`uv tool install "visio-mcp[preview] @ git+…"` then
`playwright install chromium`) or LibreOffice. SVG and the HTML viewer always work.

**No PDF.** Needs Visio or LibreOffice.

## AI providers

| Message | Fix |
|---|---|
| *check your API key: run visio-ai setup* | The key is missing, wrong or expired. |
| *rate limited* | Retried automatically three times; wait a minute or use a smaller model. |
| *model not found* | Check the model id (`visio-ai setup` → Model), or for Azure the deployment name. |
| *could not connect* | Network, proxy or endpoint URL. Ollama: is `ollama serve` running? |

The agent stops after 40 steps and submits what it has. Narrow the request with `--focus`, or
pick fewer repositories.

## Cloud icons

**`visio-ai icons install` can't reach the vendor site.** It falls back to the PyPI icons
automatically. Behind a strict proxy, download the official zip in a browser and run
`visio-ai icons install azure --from PATH`.

## Reporting a problem

Run with the spec saved (`/save` in the studio or `--save-spec`), and include the spec, the
`visio-ai doctor` output and the warnings.
