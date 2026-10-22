# Getting started

## 1. Install

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv tool install git+https://github.com/sumsam-ali-sac/visio-mcp
```

This installs two commands: `visio-ai` (the terminal app) and `visio-mcp` (the MCP server).

Check your machine:

```powershell
visio-ai doctor
```

| You have | What you get |
|---|---|
| Windows + Visio desktop (Professional / Plan 2) | Diagrams drawn **live** in your Visio window, native stencils, Visio exports (PNG, SVG, PDF, JPG) |
| Anything else | A native `.vsdx` (opens in Visio desktop or Visio for the web) plus SVG, an interactive HTML preview, and PNG/PDF when a renderer is available |

Optional extras for machines without Visio:

```powershell
uv tool install "visio-mcp[preview] @ git+https://github.com/sumsam-ali-sac/visio-mcp"
playwright install chromium     # crisp PNG previews
```

LibreOffice, if installed, is also used for PNG and PDF.

## 2. Pick an AI (optional)

```powershell
visio-ai setup
```

Choose Claude, Gemini, Azure OpenAI, OpenAI or a local Ollama model. API keys found in your
environment (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_*`, `OPENAI_API_KEY`) are
detected automatically. You can skip this: `--offline` drafts diagrams from a static scan of the
repo (manifests, docker-compose, Terraform/Bicep, Kubernetes, CI workflows).

## 3. Draw your first diagram

```powershell
visio-ai
```

Paste the path of a cloned repo (or a folder of repos), pick the diagram type (the best fit is
starred), and watch Visio draw it. Then refine it in plain words: *"group the databases"*,
*"add the Stripe webhook"*, *"switch to the azure theme"*.

No questions, for scripts:

```powershell
visio-ai draw C:\code\shop --type architecture --theme azure
```

From a spec file:

```powershell
visio-ai render examples\azure-rag-app.json
```

## 4. Cloud icons

For cloud diagrams, install the official icon sets once:

```powershell
visio-ai icons install
```

See [Cloud architecture icons](cloud-icons.md).

## 5. Use it from your AI coding app

```powershell
visio-ai handoff C:\code\shop --tool claude      # or gemini, codex, copilot
```

registers the MCP server with that app and starts it on your repo. Or wire it up yourself:
[The MCP server](mcp-server.md).

Output goes to `Documents/visio-mcp` unless you pass `--out` or set `VISIO_MCP_OUT`.
