# Entity-relationship diagram (ERD)

**Use when:** you need the entities (tables) of a data model and the relationships and cardinalities between them.

## Purpose
A logical or physical data model. Chen notation draws entities, relationships and
attributes as separate shapes; crow's-foot (Martin/IE) notation puts attributes in the
entity box and cardinality on the line ends. This server draws crow's-foot style:
entity boxes with cardinality written on the relationship edge.

## Spec settings
- `"type": "erd"`, `"layout": "flowchart-lr"`; `tree-tb` when one aggregate root owns
  the rest (Customer -> Order -> Order Line).
- Theme `professional` or `monochrome` for print.

## Node kinds
- `entity` for every table/entity. Nothing else, except an optional `note`.
- Label: singular Title Case noun (`Customer`, `Order Line`), never plural table
  names or prefixes (`tbl_customers`).
- `description`: the key attributes, short: `PK id, email, created_at`. For a
  physical model put the table name in `technology` (`sales.order_line`).
- 5-20 entities. Split by bounded context/subject area beyond that.

## Groups
Optional `generic` groups for subject areas or schemas (`Sales`, `Catalog`). Do not
nest.

## Edges (relationships)
- One edge per relationship, from the "one" side to the "many" side (parent -> child).
- Label with cardinality, UML/crow's-foot style: `1..*`, `0..1`, `1..1`, `0..*`, or
  `1:N`, `M:N` - optionally with the verb: `places 1..*` (`[erd-cardinality]`).
- `arrow: "none"` reads best for relationships (cardinality carries the direction);
  `dashed` for non-identifying/optional relationships.
- Resolve many-to-many through an associative entity (`Order Line`, `Enrollment`) in
  a physical model.

## Checklist
- [ ] Only `entity` nodes; singular names
- [ ] Every relationship labeled with cardinality
- [ ] Parent -> child direction consistent
- [ ] Key attributes in description, not in the label
- [ ] M:N resolved with an associative entity (physical models)

## Common mistakes
- Unlabeled lines - an ERD without cardinality is just boxes.
- Mixing services or APIs into the data model.
- Listing every column; keep keys and the 2-3 attributes that explain the entity.
- Plural or technical table names as labels.

## Example
```json
{
  "title": "Sales Data Model",
  "subtitle": "Logical model, crow's-foot cardinality - v4",
  "type": "erd",
  "layout": "flowchart-lr",
  "nodes": [
    {"id": "customer", "label": "Customer", "kind": "entity", "description": "PK id, email, name"},
    {"id": "order", "label": "Order", "kind": "entity", "description": "PK id, FK customer_id, placed_at"},
    {"id": "line", "label": "Order Line", "kind": "entity", "description": "PK id, FK order_id, FK product_id, qty"},
    {"id": "product", "label": "Product", "kind": "entity", "description": "PK id, sku, price"},
    {"id": "payment", "label": "Payment", "kind": "entity", "description": "PK id, FK order_id, amount"}
  ],
  "edges": [
    {"source": "customer", "target": "order", "label": "places 0..*", "arrow": "none"},
    {"source": "order", "target": "line", "label": "1..*", "arrow": "none"},
    {"source": "product", "target": "line", "label": "0..*", "arrow": "none"},
    {"source": "order", "target": "payment", "label": "0..1", "arrow": "none", "style": "dashed"}
  ]
}
```
