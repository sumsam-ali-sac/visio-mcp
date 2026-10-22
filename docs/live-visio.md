# Live Visio

On Windows with Visio desktop installed, visio-mcp drives Visio over COM and builds the diagram
in front of you.

## What you see

1. Visio comes to the front with a new drawing window, sized to the diagram, on the theme's page
   background.
2. The title block appears, then the shapes group by group, then their containers wrap around
   them (innermost first), then connectors are glued between shapes, then the legend.
3. The view zooms to fit the page and the drawing is saved as `.vsdx` with the exports you asked
   for.

Everything is a native Visio object: masters from the built-in stencils, real containers with
members, dynamic connectors glued to shapes, rich text with separate runs for the label,
technology and description. You can keep editing it by hand.

Redrawing (a patch, `/theme`, a chat edit) opens the new version in a new window. A previous
window is closed only when it is one of ours, saved, and unchanged since; otherwise it stays
open so you can compare.

## Modes

| Mode | How | Behavior |
|---|---|---|
| Live (default) | `visio-ai`, MCP server default | Starts its own visible Visio, draws with a short pause between shapes (`VISIO_MCP_LIVE_DELAY`, default 0.05 s; the CLI uses 0.06 s). |
| Attach | `--attach`, `VISIO_MCP_ATTACH=1` | Draws into the Visio you already have open (new drawing window). Your documents, stencils and settings are left alone; Visio is never quit. Falls back to starting Visio when none is running. |
| Hidden | `--no-live`, `VISIO_MCP_HEADLESS=1` | Invisible Visio, no pauses. For CI and servers. |
| Native | `--native`, `VISIO_MCP_TARGET=native` | No Visio at all: a native `.vsdx` writer plus SVG/HTML/PNG previews. |

## Stencils and fallbacks

Each kind lists Visio masters to try in order (for example `BASFLO_U.VSSX › Database`). If none
exists on the machine, the kind falls back to its base kind's shape. Cloud kinds use the official
icon packs when installed ([Cloud icons](cloud-icons.md)). Unknown kinds draw a rectangle and
warn (with a *did you mean*). `list_stencils` / `list_masters` show what's available.

## Styling details

Shapes get explicit ShapeSheet formulas (fill, line color, weight and pattern, corner rounding,
no shadow, fonts per character run, margins), so the Visio document theme doesn't override them.
Connectors are right-angle with rounded corners, line jumps where lines cross, and a background
behind labels. Labels of icon shapes are placed under the icon.

## Verifying on a Visio machine

```powershell
uv run pytest -m visio            # COM backend tests against real Visio
uv run python scripts/smoke.py    # render every example, patch, inspect, export
```
