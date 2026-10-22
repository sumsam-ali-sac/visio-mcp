# How it works

A diagram flows through the packages in one direction. Each package owns one concern and each
file does one job (its first line says which).

```
  visio-ai (cli/)                                        any MCP client (mcp/)
       │                                                         │
  repo/ ── profile repos, digest, sandboxed file access          │
       │                                                         │
  ai/   ── a model explores the code with tools ──► DiagramSpec ◄┘     spec/  the contract
                                                       │
                                  lint/  ── resolve 'auto', fix casing, check the rules (rules/)
                                                       │
                                  plan/  ── catalog/ (kinds → masters), icons/ (official icons),
                                            style/ (themes, text, sizes), layout/ (positions, routes)
                                                       │
                                                  DiagramPlan   every visual decision, made once
                                                       │
                                  output/drawer ──┬──► output/visio/  live Visio over COM
                                                  ├──► output/vsdx/   native .vsdx, no Visio
                                                  └──► output/svg/    SVG, HTML viewer, PNG
```

Lower packages never import higher ones: `spec` depends on nothing; `catalog`, `rules`, `style`
depend only on `spec`; `lint` and `icons` on those; `layout` on `spec` and `style`; `plan` on all
of the above; `output` on `plan`; `repo`, `ai`, `cli` and `mcp` sit on top.

## Packages

| Package | Job | Start reading at |
|---|---|---|
| `spec/` | The diagram contract: `DiagramSpec`, nodes, edges, groups (`diagram.py`), patch ops (`patch.py`), `RenderResult` (`result.py`), applying patches (`edit.py`) | `diagram.py` |
| `catalog/` | 179 shape kinds: data types (`model.py`), stencils, generic and cloud kinds, aliases, `lookup`/`resolve`, listings for prompts | `resolve.py` |
| `rules/` | Ground rules per diagram type and cloud provider (markdown) and their loader | `__init__.py` |
| `lint/` | `normalize` (infer type/layout/theme, casing) and `lint` (one `checks_*.py` file per family of rules, run by `report.py`) | `normalize.py`, `report.py` |
| `style/` | Style dataclasses (`model.py`), the eight themes (`themes.py`), casing and text metrics (`text.py`), node footprints (`sizing.py`) | `themes.py` |
| `icons/` | Official Azure/AWS/GCP icon packs: where they come from (`sources.py`), installing (`install.py`), the kind → icon table (`names.py`), lookup, rasterizing | `lookup.py` |
| `layout/` | Group-aware layout engines (layered, compound, tree, swimlane, radial, manual) and routing; `compute.py` picks one | `compute.py` |
| `plan/` | `build_plan`: resolve kinds, size and lay out nodes, style everything, title and legend; `audit.py` checks the geometry | `build.py` |
| `output/` | `Drawer` (`drawer.py`) picks live Visio or native output; `native.py`, `files.py`, `detect.py`, `result.py` | `drawer.py` |
| `output/visio/` | The `VisioBackend` protocol (`backend.py`), `VisioCom` composed from app, document, page, shapes, text, connectors, containers and cells modules; drawing a plan (`draw.py`); editing opened files; `com_thread.py` | `draw.py`, `com.py` |
| `output/vsdx/` | Writing a `.vsdx` package: OPC parts, geometry sections, nodes, connectors, containers, images, decorations | `writer.py` |
| `output/svg/` | SVG rendering (canvas, shapes, nodes, edges, decorations, text), the HTML viewer, PNG rasterizing | `render.py` |
| `repo/` | Discover and profile repos (`detect/` has one detector per concern, IaC parsers under `detect/iac/`), digests for the AI, sandboxed `RepoFS`, secret redaction, no-AI drafts (`draft/`) | `discover.py`, `detect/scan.py` |
| `ai/` | Provider config, provider adapters (`providers/`: one file per vendor plus errors/retry and the factory), the agent (`agent.py`) with its tools, submission checks and prompts | `agent.py` |
| `cli/` | `visio-ai`: the parser (`parser.py`), dispatch (`main.py`), one module per command (`commands/`), the interactive studio (`studio/`), terminal UI and prompts | `main.py`, `studio/flow.py` |
| `mcp/` | The MCP server: tool wrappers (`server.py`), the lazily created Drawer (`state.py`), the authoring guide | `server.py` |

Tests mirror the packages: `tests/<package>/test_<module>.py` (pytest runs with
`--import-mode=importlib`). `tests/fake_visio.py` is an in-memory `VisioBackend` that records every
call, so everything except the real COM layer is tested without Visio.

## Extending

**A shape kind.** Generic kinds live in `catalog/generic.py`, cloud kinds in `catalog/cloud.py`:
give a category from `style.CATEGORIES`, a geometry from `style.GEOMETRY_MIN`, Visio master
candidates (first available wins) and, for cloud kinds, a base kind and glyph. Add its icon
names to `icons/names.py`. Run `uv run pytest tests/catalog tests/icons` and
`uv run python scripts/gen_docs.py`.

**A theme.** Add a `Theme` to `style/themes.py` (derive from an existing one with `replace`)
and register it in `THEMES`.

**A diagram type.** Add it to `DiagramType` in `spec/diagram.py`, write `rules/<type>.md`
(start with a `**Use when:**` line, end with a JSON example), teach `lint/infer.py` how to
recognize it and which layout it gets, and add checks in the matching `lint/checks_*.py`.

**A lint rule.** Write a check function in the right `lint/checks_*.py`, add it to `CHECKS` in
`lint/report.py` and its code to `RULE_CODES` in `lint/finding.py`.

**A layout.** Add an engine module in `layout/` and route the preset to it in
`layout/compute.py`. `tests/plan/test_audit.py` audits every example under every layout.

**An output format.** Write an emitter that takes a `DiagramPlan` (see `output/svg/render.py`
for the smallest one) and call it from `output/native.py`.

**A repo detector.** Add a module to `repo/detect/` (or an IaC parser to `repo/detect/iac/`)
and call it from `repo/detect/scan.py`.

**An AI provider.** Implement `LLM.start(system, tools) -> Session` with `send_user` and
`send_tool_results` in a new `ai/providers/<vendor>.py`, keeping the vendor's native message
history, map its errors in `ai/providers/errors.py`, and register it in
`ai/providers/factory.py` and `ai/config.py`.

**A CLI command.** Add `cli/commands/<name>.py` with `run(args) -> int`, its flags in
`cli/parser.py`, and a line in `cli/commands/help.py`.

## Tests

```powershell
uv run pytest              # 1,200+ tests, no Visio needed
uv run pytest -m visio     # the COM layer against real Visio, on Windows
uv run python scripts/smoke.py   # every example drawn live, patched, inspected, exported
```
