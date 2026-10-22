# visio-mcp

An MCP server that draws native, editable Microsoft Visio diagrams from a semantic spec.
Agents describe *what* is in a diagram (nodes, edges, groups, layout); the server lays it
out and drives Visio over COM to produce a `.vsdx`, plus PNG/SVG/PDF exports.

```
MCP client ──► visio-mcp ──► Visio (COM) ──► .vsdx / .png
(Claude Code, Copilot, VS Code, Codex, custom agents)
```

Why: LLM agents can read a repo and understand it, but placing shapes by coordinates gives
messy, overlapping diagrams that take dozens of tool calls. Here the model writes one spec,
the layout engine places everything, and the agent reviews a preview and patches what is left.

## Requirements

- Windows with Microsoft Visio (Professional or Plan 2), desktop edition
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install

```powershell
git clone https://github.com/sumsam-ali-sac/visio-mcp
cd visio-mcp
uv sync
```

## Connect it

**Claude Code**

```powershell
claude mcp add visio -- uv --directory C:/path/to/visio-mcp run visio-mcp
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "visio": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "C:/path/to/visio-mcp", "run", "visio-mcp"]
    }
  }
}
```

**GitHub Copilot CLI** (`~/.copilot/mcp-config.json`)

```json
{
  "mcpServers": {
    "visio": {
      "type": "local",
      "command": "uv",
      "args": ["--directory", "C:/path/to/visio-mcp", "run", "visio-mcp"],
      "tools": ["*"]
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`)

```toml
[mcp_servers.visio]
command = "uv"
args = ["--directory", "C:/path/to/visio-mcp", "run", "visio-mcp"]
```

Any MCP client works with any model, for example an agent on Azure OpenAI. The server is
plain stdio MCP; the client brings the model.

## Usage

Ask the client to use the `diagram` prompt (it explores a repo or draws from a description):

> Use the visio `diagram` prompt with source "repo" on `C:/code/payments`, a context diagram
> of the system and its external dependencies.

Or just ask in plain language:

> Draw a flowchart of our CI pipeline: build, test, a decision on test results, scan, deploy to staging, then production.

The agent then calls `get_authoring_guide`, writes one spec, calls `render_diagram` once,
and refines with `patch_diagram` until the preview is clean.

### Spec format

A `DiagramSpec` is a small JSON document:

```json
{
  "title": "Order service",
  "layout": "flowchart-lr",
  "groups": [{"id": "core", "label": "Core"}],
  "nodes": [
    {"id": "user", "label": "Customer", "kind": "user"},
    {"id": "api", "label": "Orders API", "kind": "api", "group": "core"},
    {"id": "db", "label": "Orders DB", "kind": "database", "group": "core"}
  ],
  "edges": [
    {"source": "user", "target": "api", "label": "HTTPS"},
    {"source": "api", "target": "db", "label": "SQL"}
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `title` | string | Page title; default file name |
| `layout` | enum | See layouts below; default `flowchart-tb` |
| `nodes` | list, min 1 | `id` (unique), `label`, `kind`, `group`, `fill` (`#RRGGBB`), `x`/`y` (only for `none`) |
| `edges` | list | `source`, `target`, `label`, `style` (`solid`/`dashed`/`dotted`), `arrow` (`end`/`both`/`none`) |
| `groups` | list | Containers: `id`, `label`. A node joins one group via `group` |

Ids must not clash between nodes and groups. Edges must reference existing nodes.

### Layouts

| Layout | Use for |
|---|---|
| `flowchart-tb` | Processes, pipelines, decisions (default) |
| `flowchart-lr` | Architecture and data flow, left to right |
| `tree-tb` / `tree-lr` | Hierarchies, org charts |
| `radial` | Hub and spokes |
| `circular` | Rings |
| `compact` | Indented tree, root top-left |
| `none` | Keep your own `x`/`y` |

### Patch operations

`patch_diagram` takes a list of ops, applied in order:

| `op` | Effect |
|---|---|
| `add_node` | Add a node (same fields as a spec node) |
| `update_node` | Change `label` or `fill` of node `id` |
| `remove` | Delete a node, group, or edge (`"source->target"`) |
| `add_edge` | Add an edge |
| `move` | Move one shape to `x`, `y` |
| `relayout` | Re-run auto-layout with a new `layout` |

Kinds (node `kind`) include `process`, `decision`, `start`, `end`, `service`, `api`,
`database`, `queue`, `cache`, `user`, `server`, `firewall`, `entity`, and more. Call
`list_kinds` for the full list with descriptions.

## Tools

| Tool | What it does |
|---|---|
| `render_diagram` | Draw a whole spec in one call; saves `.vsdx` and exports; returns overlaps, warnings, and a PNG preview |
| `patch_diagram` | Apply patch ops to the open diagram, then re-save and re-export |
| `inspect_diagram` | List shapes, connectors, and overlapping pairs on the open page |
| `open_diagram` | Open an existing `.vsdx` for inspection and patching |
| `export_diagram` | Export the open page to png, svg, pdf, or jpg |
| `list_kinds` | Semantic node kinds and what each is for |
| `list_stencils` | Built-in Visio stencil files on this machine |
| `list_masters` | Master shapes inside a stencil (to diagnose fallbacks) |
| `get_authoring_guide` | How to write a good spec and run the review loop |

Prompt: `diagram` (`subject`, `source` = `prompt` or `repo`).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VISIO_MCP_OUT` | `./diagrams` | Directory for `.vsdx` and exports |
| `VISIO_MCP_VISIBLE` | unset | Set to `1` to watch Visio draw the diagram |

## Development

```powershell
uv run pytest            # unit tests, no Visio needed
uv run pytest -m visio   # real Visio tests (needs Visio installed)
```

## License

MIT
