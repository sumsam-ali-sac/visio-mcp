# The MCP server

`visio-mcp` is a stdio MCP server. Any MCP client (Claude Code, Claude Desktop, VS Code / GitHub
Copilot, Copilot CLI, Codex, Gemini CLI, Cursor, custom agents on any model) can use it to draw
professional Visio diagrams.

## Connect

Run straight from GitHub with `uvx` (nothing to install), or point at a clone with
`uv --directory C:/path/to/visio-mcp run visio-mcp`.

```powershell
claude mcp add visio -- uvx --from git+https://github.com/sumsam-ali-sac/visio-mcp visio-mcp
```

**VS Code** — `.vscode/mcp.json`

```json
{
  "servers": {
    "visio": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sumsam-ali-sac/visio-mcp", "visio-mcp"],
      "env": {"VISIO_MCP_OUT": "${workspaceFolder}/docs/diagrams"}
    }
  }
}
```

**Claude Desktop** — `claude_desktop_config.json`

```json
{"mcpServers": {"visio": {"command": "uvx",
  "args": ["--from", "git+https://github.com/sumsam-ali-sac/visio-mcp", "visio-mcp"]}}}
```

Copilot CLI, Codex and Gemini CLI: see the README, or let `visio-ai handoff` write the config.

## How an agent should use it

1. `get_authoring_guide` once, then `get_diagram_rules(type)` for the diagram type.
2. Write one complete `DiagramSpec` ([guide](spec.md)). Optionally `lint_diagram(spec)`.
3. `render_diagram(spec, name)` once. With Visio it is drawn live in the user's Visio window.
   The reply is a JSON summary plus a PNG preview image:

   ```json
   {"shapes": 14, "connectors": 11, "warnings": [], "suggestions": ["[edge-labels] …"],
    "overlaps": [], "files": ["C:/Users/me/Documents/visio-mcp/shop.vsdx", "…/shop.png"]}
   ```

4. Review: `overlaps` must be empty; fix `warnings` and `suggestions` with **one**
   `patch_diagram` batch per pass; stop after at most three passes.

The `diagram(subject, source, diagram_type)` prompt packages these steps; with `source="repo"`
it also tells the agent where to look in a repository.

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `get_authoring_guide` | | How to write a great spec, the review loop, an example |
| `get_diagram_rules` | `diagram_type`, `provider?` | Ground rules, checklist and example spec for a type; `provider` (`azure`/`aws`/`gcp`) adds cloud conventions |
| `list_kinds` | `provider?` | Shape kinds by category (+ that provider's services) |
| `list_themes` | | Theme names and when to use them |
| `lint_diagram` | `spec` | Resolved type/layout/theme, normalization notes, rule findings — nothing is drawn |
| `render_diagram` | `spec`, `name?`, `formats=["png"]`, `preview=true` | Summary + preview image; saves `.vsdx` and exports |
| `patch_diagram` | `ops`, `formats?`, `preview=true` | Same as render, after editing the open diagram |
| `inspect_diagram` | | Shapes with positions and sizes, connectors, overlaps |
| `open_diagram` | `path` | Opens an existing `.vsdx` (needs Visio) for inspect/patch/export |
| `export_diagram` | `format`, `path?` | `png`, `svg`, `pdf`, `jpg`, `html`; returns the file path |
| `install_icons` | `provider="all"` | Installs official cloud icon packs; returns status |
| `list_stencils`, `list_masters` | `stencil` | Diagnose which Visio stencils exist on this machine |

**Patch ops** (`patch_diagram`), applied in order; a bad op becomes a warning and the rest still
apply:

| op | Fields |
|---|---|
| `add_node` | `node` |
| `update_node` | `id`, any of `label`, `kind`, `group` (`""` = no group), `technology`, `description`, `emphasis`, `fill` |
| `remove` | `id` of a node, group, or edge (`source->target`, `source->target#2` for repeats) |
| `add_edge` | `edge` |
| `update_edge` | `id`, any of `label`, `style`, `arrow`, `color` |
| `add_group` | `group`, `members` (node ids to move in) |
| `update_diagram` | any of `title`, `subtitle`, `theme`, `layout`, `legend` |
| `relayout` | `layout` |
| `move` | `id`, `x`, `y` (inches; applied after the redraw, not kept on the next relayout) |

A diagram rendered in the session is edited as a spec and redrawn, so layout and styling stay
consistent. A diagram opened from disk is edited shape by shape (only label, fill, remove, add
and move apply; layout and theme changes need a diagram drawn from a spec).

**Resources:** `visio://rules/{diagram_type}` — the same text as `get_diagram_rules`.

## Configuration

| Variable | Default | |
|---|---|---|
| `VISIO_MCP_OUT` | `Documents/visio-mcp` | Output folder |
| `VISIO_MCP_TARGET` | `auto` | `visio` (require Visio), `native` (never use Visio), `auto` |
| `VISIO_MCP_LIVE` | `1` | Draw in the visible Visio window, shape by shape |
| `VISIO_MCP_LIVE_DELAY` | `0.05` | Seconds between shapes while drawing live |
| `VISIO_MCP_ATTACH` | `0` | `1`: draw into the Visio instance the user already has open |
| `VISIO_MCP_HEADLESS` | `0` | `1`: hidden Visio (servers, CI) |
| `VISIO_MCP_ICONS` | user cache | Where cloud icon packs live |

Without Visio (macOS, Linux, no license) the server still works: it writes a native `.vsdx`
and previews. `open_diagram` needs Visio.
