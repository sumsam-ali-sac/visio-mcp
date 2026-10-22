# visio-mcp — architecture & feature list

PRD: `visio-mcp.prd.md` (milestones 1–3; milestone 4 later).

## Architecture (fixed contracts — do not change without the planner)

```
MCP client ──stdio──► server.py (thin tools)
                        │ com_thread.call(...)  ← every Visio call on ONE thread (CoInitialize)
                        ▼
               render.py / edit.py  ── talk only to ──►  backend.VisioBackend (Protocol)
                        │                                   ├─ visio_com.VisioCom   (real, COM)
                        ▼                                   └─ tests/fake_visio.FakeVisio
               catalog.py (kind → stencil/master)
               prompts.py (authoring guide + MCP prompt)
```

- `spec.py` — DiagramSpec, PatchOp, RenderResult (pydantic). Done.
- `backend.py` — VisioBackend Protocol + ShapeInfo. Shapes addressed by **name** (= node/group id; connectors `source->target`). Inches, center pin, bottom-left origin. Done.
- `com_thread.py`, `server.py`, `tests/fake_visio.py`, `tests/test_spec.py` — done.

## Features (independent, disjoint files)

| # | Feature | Owns files | Model |
|---|---|---|---|
| F1 | Shape catalog | `src/visio_mcp/catalog.py`, `tests/test_catalog.py` | sonnet |
| F2 | Visio COM backend | `src/visio_mcp/visio_com.py`, `tests/test_visio_com.py` (marked `visio`) | sonnet |
| F3 | Render, patch, inspect | `src/visio_mcp/render.py`, `src/visio_mcp/edit.py`, `tests/test_render.py`, `tests/test_edit.py` | sonnet |
| F4 | Authoring prompt, examples, docs | `src/visio_mcp/prompts.py`, `examples/*.json`, `README.md`, `tests/test_examples.py` | haiku |

F3 imports `catalog.resolve`; its tests may monkeypatch it until F1 lands.

## Done when
- `uv run pytest` green (fake backend); `uv run pytest -m visio` green on a machine with Visio.
- Each example in `examples/` renders with 0 overlaps in real Visio.
- Works from Claude Code via `claude mcp add visio -- uv --directory <repo> run visio-mcp`.
