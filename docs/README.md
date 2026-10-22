# visio-mcp documentation

| Guide | |
|---|---|
| [Getting started](getting-started.md) | Install, first diagram in two minutes, with or without Visio |
| [The visio-ai terminal app](cli.md) | The studio, every command and flag, AI providers, handing off to Claude Code / Gemini CLI / Codex / Copilot |
| [The MCP server](mcp-server.md) | Connect any MCP client, tools, resources, environment variables |
| [Writing diagram specs](spec.md) | The DiagramSpec, groups and nesting, patch operations, review loop |
| [Diagram types and ground rules](reference/diagram-types.md) | Conventions for the 14 diagram types the AI follows and the linter checks |
| [Cloud architecture icons](cloud-icons.md) | Official Azure, AWS and Google Cloud icons |
| [Live Visio](live-visio.md) | How live drawing and attaching to your open Visio work |
| [Themes](reference/themes.md) | The eight themes, their fonts and palettes |
| [Shape kinds](reference/kinds.md) | All shape kinds, cloud services and aliases |
| [How it works](architecture.md) | The pipeline, module map, and how to extend it (kinds, themes, layouts, providers) |
| [Troubleshooting](troubleshooting.md) | Visio not found, COM errors, previews, provider errors |

JSON schemas for tooling: [diagram-spec.schema.json](reference/diagram-spec.schema.json),
[patch-ops.schema.json](reference/patch-ops.schema.json).

Reference pages under `reference/` are generated: `uv run python scripts/gen_docs.py`.
