# visio-mcp

## Problem
Engineers who must deliver diagrams in Microsoft Visio (architecture, flowcharts, deployment, org charts) draw them by hand, and the diagrams go stale as the code changes. LLM agents can read a repo or a prompt and understand the system, but they have no reliable way to produce a native, editable Visio file. Existing Visio MCP servers target Azure architecture only and make the model place every shape by coordinates, which yields overlapping, messy diagrams and dozens of slow tool calls.

## Evidence
- Observed: the closest existing project (iakov-gan/mcp-server-visio) only offers basic shapes plus Azure icons, has no auto-layout, and needs one tool call per shape.
- Visio is a hard requirement for the owner (deliverables must be .vsdx).
- Assumption: LLMs produce better diagrams when they describe *meaning* (nodes, edges, groups) instead of geometry — needs validation via prototype comparison.

## Users
- **Primary**: a developer using an MCP client (Claude Code, Copilot CLI, VS Code agent mode, Codex, or a custom Azure OpenAI agent) who wants a Visio diagram of a repo they are building or of a system described in a prompt.
- **Not for**: people without Visio desktop on Windows; teams wanting web-based diagram tools (draw.io, Mermaid).

## Hypothesis
We believe **a model-agnostic MCP server that turns a semantic diagram spec into a laid-out, native Visio diagram** will **let any agent produce presentable Visio diagrams in one step** for **developers who live in MCP clients**.
We'll know we're right when **a 20–40 node diagram renders from one spec with no overlapping shapes, and needs at most 2 refinement passes to look presentable**.

## Success Metrics
| Metric | Target | How measured |
|---|---|---|
| Tool calls to render a full diagram | 1 | count calls for sample specs |
| Overlapping shapes after auto-layout | 0 on sample specs | automated bounding-box check |
| Diagram types supported in MVP | ≥ 5 (architecture, flowchart, network/deployment, org chart, ERD-style) | sample spec gallery |
| Clients verified | ≥ 2 (Claude Code + one OpenAI-model client) | manual run |

## Scope
**MVP** — one-call render of a semantic spec (nodes, edges, groups/containers, layout style) into Visio with built-in stencils and auto-layout; small edit operations to refine; export to PNG/SVG/PDF and save .vsdx; discovery of stencils/masters; a built-in authoring prompt so any client knows how to explore a repo or prompt and write a good spec.

**Out of scope**
- Our own LLM/agent app — clients bring the model; MCP keeps it portable.
- Repo parsers/extractors (docker-compose, ORM, OpenAPI) — the client agent explores the repo.
- Sequence diagrams and swimlanes — Visio's layout engine can't do them well; later milestone.
- macOS/Linux or Visio for the web — COM is Windows-only.
- Theme designer / custom styling UI — a small set of fixed themes is enough.

## Delivery Milestones
| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Render from spec | A JSON spec becomes a laid-out .vsdx + PNG in one call | complete | visio-mcp.plan.md |
| 2 | Refine & inspect | Agent can list, patch and re-layout shapes, then re-export | complete | visio-mcp.plan.md |
| 3 | Portable authoring | Built-in prompt + examples work in Claude Code and an Azure OpenAI client | in-progress (prompt + examples done; client runs not yet verified) | visio-mcp.plan.md |
| 4 | Sequence / swimlane | Custom layout for diagram types Visio can't auto-layout | pending | — |

## Open Questions
- [ ] Is a Visio license available on the owner's account (Plan 2 / Professional)? Without it COM automation may be limited.
- [ ] Which Visio edition is installed — Standard lacks many stencils (network, UML, database).
- [ ] Do the target clients (Copilot CLI, Codex) support MCP *prompts*, or only tools? If tools only, the prompt must also be exposed as a tool or doc.
- [ ] Does the chosen Azure OpenAI model accept image input for the PNG review loop?

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Visio not installed/licensed on dev machine | High (currently) | High | Fake COM layer for tests; real-Visio smoke test script |
| COM is slow / flaky on large diagrams | Med | Med | Disable screen updating during render; single-call render |
| Built-in layout gives poor results for some types | Med | Med | Per-type layout presets; patch tools for manual fixes |
| Stencil/master names differ by Visio version/locale | Med | Med | Resolve via semantic catalog with fallbacks to basic shapes |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
