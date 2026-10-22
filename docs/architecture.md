# How it works

```
            visio-ai (terminal)                         any MCP client
                  │                                           │
   scanner ──► ai.agent (Claude/Gemini/Azure/OpenAI/Ollama)    │
   (repos,       explores code with sandboxed tools           │
    digest)            │                                      │
                       ▼                                      ▼
                  DiagramSpec  ◄──────────────────────── server.py tools
                       │
         lint.normalize (type, layout, theme, casing) + lint.lint (rule findings)
                       │
   plan.build_plan ── catalog (kind → master/geometry/category) ── icons (official cloud icons)
                  ├── style  (theme, fonts, text metrics, node sizes)
                  ├── layout (group-aware layered/tree/swimlane/radial/grid + orthogonal routes)
                  └── title block, legend, page size
                       │
                  DiagramPlan  (every visual decision, made once)
                       │
        engine.Drawer ─┼─► render.emit_visio ─► backend (visio_com over COM: live / attach / hidden)
                       ├─► vsdx_writer      ─► native .vsdx (no Visio needed)
                       └─► svg              ─► SVG, HTML viewer, PNG
```

## Modules

| Module | Responsibility |
|---|---|
| `spec.py` | `DiagramSpec`, nodes, edges, groups, patch ops, `RenderResult` (pydantic) |
| `lint.py` | `normalize` (resolve `auto`, casing, labels) and `lint`/`findings` (rule codes) |
| `rules.py`, `rules/*.md` | Ground rules per diagram type and cloud provider |
| `catalog.py` | 179 kinds: description, category, geometry, provider, base kind, glyph, Visio master candidates; `resolve`, `lookup`, `describe_kinds` |
| `icons.py` | Install, index and look up official cloud icon packs |
| `style.py` | Themes, `title_case`/`sentence_case`, text metrics, `node_size` |
| `layout/` | `compute_layout(spec, sizes, group_styles, layout)` → node rects, group frames, routes |
| `plan.py` | `build_plan(spec, has_master)` → `DiagramPlan` |
| `geometry_check.py` | `audit(plan)`: overlaps, group containment, edges through nodes, off-page |
| `render.py` | Draws a plan through the `VisioBackend` protocol, in watchable order |
| `backend.py` | The `VisioBackend` protocol (shapes addressed by spec id) |
| `visio_com.py` | `VisioBackend` over COM (pywin32); live, attach and hidden modes |
| `com_thread.py` | Keeps every COM call on one thread |
| `vsdx_writer.py` | Writes a `.vsdx` package from a plan, standard library only |
| `svg.py` | SVG, HTML viewer, PNG rasterization |
| `engine.py` | `Drawer`: Visio or native, render/patch/open/export, file naming |
| `edit.py` | Patch ops on a spec (redraw) or on shapes (opened files); `inspect` |
| `scanner/` | Repo discovery, profiling (stack, cloud, IaC, CI, data stores), digests, `RepoFS`, no-AI drafts |
| `ai/` | Provider config, provider adapters, the exploring `DiagramAgent` and its prompts |
| `cli/` | The `visio-ai` app: studio, commands, handoff, UI kit |
| `server.py` | The MCP server |

## Extending

**A shape kind.** Add a `_k(...)` (generic) or `_c(...)` (cloud) entry in `catalog.py` with a
category from `style.CATEGORIES`, a geometry from `style.GEOMETRY_MIN`, Visio master candidates
(first available wins) and, for cloud kinds, a base kind and glyph. Add its icon names in
`icons.py`. Run `uv run pytest tests/test_catalog.py tests/test_icons.py` and
`uv run python scripts/gen_docs.py`.

**A theme.** Add a `Theme` in `style.py` (style every category and group kind, or derive from an
existing theme with `replace`) and register it in `THEMES`.

**A diagram type.** Add it to `DiagramType` in `spec.py`, write `rules/<type>.md` (start with a
`**Use when:**` line, end with a JSON example), teach `lint.normalize` how to infer it and which
layout/theme it gets, and add rules to `lint.py` if needed.

**A layout.** Add a module in `layout/` returning node rects, group frames and routes; register
it in `compute_layout`. `tests/test_layout.py` runs `geometry_check.audit` on every example under
every layout.

**An AI provider.** Implement `LLM.start(system, tools) -> Session` with `send_user` and
`send_tool_results` in `ai/providers.py`, keeping the provider's native message history, and map
errors to `LLMError`. Register it in `make_llm` and `ai/config.py`.

## Tests

```powershell
uv run pytest              # ~600 tests, no Visio needed (FakeVisio records every backend call)
uv run pytest -m visio     # real Visio over COM, on Windows
```
