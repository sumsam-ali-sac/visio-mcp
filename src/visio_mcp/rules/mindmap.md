# Mind map

**Use when:** you need to break one central topic into themes and ideas (brainstorms, capability maps, scoping).

## Purpose
A radial breakdown of one central idea into branches and sub-branches (Tony Buzan's
mind map, used in workshops and scoping). It answers "what are the parts of this
topic?" and is the right tool for early discovery, capability maps and agendas - not
for flows or systems.

## Spec settings
- `"type": "mindmap"`, `"layout": "radial"` (center in the middle). `tree-lr` reads
  better when branches carry long lists.
- Theme `professional`; `legend: false`.

## Node kinds
- The center: `mindmap-root` with `emphasis: true` - the topic in 1-3 words.
- Main branches: `box` (or `process`), one per theme, 3-7 branches.
- Leaves: `box` or `note`; 1-4 words each, keywords not sentences.
- No architecture or flowchart kinds; this is a thinking tool, not a system view.

## Groups
None. Branches *are* the grouping. Use `fill` only to color whole branches
consistently if needed (and then at most a few distinct colors).

## Edges
- Center -> branch -> leaf, always outward. No labels.
- `arrow: "none"` - a mind map shows association, not flow.
- No cross-links between branches; if you need them, you need another diagram type.

## Checklist
- [ ] One center, 3-7 main branches, 2 levels deep (3 at most)
- [ ] Keywords, not sentences
- [ ] Undirected edges, no labels
- [ ] Balanced branches (split a branch that dominates)
- [ ] 10-30 nodes

## Common mistakes
- Sentences as nodes.
- Deep chains (5+ levels) that turn the map into a tree diagram.
- Arrows and labels on edges that imply a process.
- Several centers.

## Example
```json
{
  "title": "Cloud Migration Scope",
  "subtitle": "Discovery workshop - Oct 2026",
  "type": "mindmap",
  "layout": "radial",
  "legend": false,
  "nodes": [
    {"id": "center", "label": "Cloud Migration", "kind": "mindmap-root", "emphasis": true},
    {"id": "apps", "label": "Applications", "kind": "box"},
    {"id": "data", "label": "Data", "kind": "box"},
    {"id": "people", "label": "People", "kind": "box"},
    {"id": "security", "label": "Security", "kind": "box"},
    {"id": "rehost", "label": "Rehost Legacy ERP", "kind": "note"},
    {"id": "refactor", "label": "Refactor Web Shop", "kind": "note"},
    {"id": "dw", "label": "Move Warehouse", "kind": "note"},
    {"id": "training", "label": "Cloud Training", "kind": "note"},
    {"id": "identity", "label": "Single Sign-On", "kind": "note"}
  ],
  "edges": [
    {"source": "center", "target": "apps", "arrow": "none"},
    {"source": "center", "target": "data", "arrow": "none"},
    {"source": "center", "target": "people", "arrow": "none"},
    {"source": "center", "target": "security", "arrow": "none"},
    {"source": "apps", "target": "rehost", "arrow": "none"},
    {"source": "apps", "target": "refactor", "arrow": "none"},
    {"source": "data", "target": "dw", "arrow": "none"},
    {"source": "people", "target": "training", "arrow": "none"},
    {"source": "security", "target": "identity", "arrow": "none"}
  ]
}
```
