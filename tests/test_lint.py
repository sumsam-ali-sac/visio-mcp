import pytest

from visio_mcp import lint
from visio_mcp.spec import DiagramSpec


def make(nodes, edges=(), groups=(), **kw) -> DiagramSpec:
    kw.setdefault("title", "Test Diagram")
    kw.setdefault("subtitle", "Scope - v1")
    return DiagramSpec.model_validate({
        "nodes": [n if isinstance(n, dict) else {"id": n[0], "kind": n[1], **(n[2] if len(n) > 2 else {})}
                  for n in nodes],
        "edges": [e if isinstance(e, dict) else {"source": e[0], "target": e[1], "label": e[2] if len(e) > 2 else ""}
                  for e in edges],
        "groups": list(groups),
        **kw,
    })


def norm(spec: DiagramSpec) -> DiagramSpec:
    return lint.normalize(spec)[0]


def codes(spec: DiagramSpec) -> list[str]:
    return [f.code for f in lint.findings(norm(spec))]


def clean_arch(**kw) -> DiagramSpec:
    return make(
        [("user", "user"), ("web", "webapp"), ("api", "api"), ("db", "database")],
        [("user", "web", "HTTPS"), ("web", "api", "REST"), ("api", "db", "SQL")],
        type="architecture", **kw,
    )


def clean_flow(**kw) -> DiagramSpec:
    return make(
        [("s", "start"), ("a", "process"), ("d", "decision"), ("b", "process"), ("e", "end")],
        [("s", "a"), ("a", "d"), ("d", "b", "yes"), ("d", "e", "no"), ("b", "e")],
        type="flowchart", **kw,
    )


# --- type inference --------------------------------------------------------------------------


@pytest.mark.parametrize("expected,nodes,groups", [
    ("flowchart", [("s", "start"), ("d", "decision"), ("e", "end")], []),
    ("erd", [("a", "entity"), ("b", "entity")], []),
    ("org", [("ceo", "executive"), ("m", "manager"), ("p", "position")], []),
    ("cloud", [("u", "user"), ("f", "azure-functions"), ("db", "azure-cosmos-db")], []),
    ("cloud", [("f", "aws-lambda"), ("s", "aws-s3")], []),
    ("c4-context", [("u", "person"), ("s", "system"), ("x", "external-system")], []),
    ("c4-container", [("u", "person"), ("api", "api", {"group": "sys"})], [{"id": "sys", "kind": "system"}]),
    ("network", [("r", "router"), ("sw", "switch"), ("pc", "pc")], []),
    ("swimlane", [("a", "process", {"group": "l1"}), ("b", "process", {"group": "l2"})],
     [{"id": "l1", "kind": "lane"}, {"id": "l2", "kind": "lane"}]),
    ("state", [("i", "initial"), ("s", "state"), ("f", "final")], []),
    ("mindmap", [("c", "mindmap-root"), ("a", "box")], []),
    ("pipeline", [("b", "build"), ("t", "test"), ("d", "deploy")], []),
    ("deployment", [("api", "api", {"group": "k"}), ("db", "database")], [{"id": "k", "kind": "cluster"}]),
    ("dataflow", [("src", "external"), ("etl", "etl"), ("dw", "data-warehouse")], []),
    ("architecture", [("u", "user"), ("api", "api"), ("db", "database")], []),
])
def test_infer_type(expected, nodes, groups):
    spec, notes = lint.normalize(make(nodes, groups=groups))
    assert spec.type == expected
    assert f"type auto -> {expected}" in notes


def test_explicit_type_kept():
    spec, notes = lint.normalize(make([("s", "start"), ("e", "end")], [("s", "e")], type="pipeline"))
    assert spec.type == "pipeline"
    assert not any(n.startswith("type") for n in notes)


def test_unknown_kinds_fall_back_by_prefix():
    info = lint.kind_info("gcp-something-new")
    assert info.provider == "gcp" and not info.known


# --- layout / theme ---------------------------------------------------------------------------


@pytest.mark.parametrize("dtype,layout", sorted(lint.LAYOUTS.items()))
def test_layout_per_type(dtype, layout):
    assert norm(make([("a", "process")], type=dtype)).layout == layout


def test_explicit_layout_kept():
    assert norm(make([("a", "process")], type="architecture", layout="radial")).layout == "radial"


@pytest.mark.parametrize("kinds,theme", [
    (["azure-functions", "azure-cosmos-db", "aws-s3"], "azure"),
    (["aws-lambda", "aws-s3"], "aws"),
    (["gcp-cloud-run", "gcp-bigquery"], "gcp"),
    (["service"], "professional"),
])
def test_cloud_theme_by_dominant_provider(kinds, theme):
    spec = make([(f"n{i}", k) for i, k in enumerate(kinds)], type="cloud")
    assert norm(spec).theme == theme


@pytest.mark.parametrize("dtype,theme", [("c4-context", "c4"), ("c4-container", "c4"),
                                         ("architecture", "professional"), ("flowchart", "professional")])
def test_theme_per_type(dtype, theme):
    assert norm(make([("a", "process")], type=dtype)).theme == theme


def test_explicit_theme_kept():
    assert norm(make([("a", "aws-lambda")], type="cloud", theme="dark")).theme == "dark"


# --- casing / labels --------------------------------------------------------------------------


def test_casing_and_whitespace():
    spec = make(
        [("api", "api", {"label": "  orders   api ", "technology": " Python  / FastAPI "}),
         ("orders_db", "database"), ("paymentService", "service")],
        [("api", "orders_db", "Reads From"), ("api", "paymentService", " HTTPS ")],
        [{"id": "data_tier", "kind": "tier", "label": ""}],
        title="  My   Title ",
    )
    out, notes = lint.normalize(spec)
    labels = {n.id: n.label for n in out.nodes}
    assert labels == {"api": "Orders API", "orders_db": "Orders DB", "paymentService": "Payment Service"}
    assert out.nodes[0].technology == "Python / FastAPI"
    assert [e.label for e in out.edges] == ["reads from", "HTTPS"]
    assert out.groups[0].label == "Data Tier"
    assert out.title == "My Title"
    assert sum("recased" in n for n in notes) == 1
    assert any("filled 3 empty" in n for n in notes)


def test_empty_edge_labels_not_invented():
    out = norm(clean_flow())
    assert out.edges[0].label == ""


def test_normalize_returns_new_spec():
    spec = make([("a", "process", {"label": "do thing"})])
    out = norm(spec)
    assert spec.nodes[0].label == "do thing" and spec.type == "auto"
    assert out.nodes[0].label == "Do Thing"


def test_normalize_is_idempotent():
    once = norm(clean_arch())
    twice, notes = lint.normalize(once)
    assert twice == once and notes == []


# --- lint: clean specs ------------------------------------------------------------------------


def test_clean_specs_have_no_findings():
    assert lint.lint(norm(clean_arch())) == []
    assert lint.lint(norm(clean_flow())) == []


def test_finding_format():
    out = lint.lint(norm(make([("a", "process"), ("b", "process"), ("c", "process")], [("a", "b")],
                              type="architecture")))
    assert out == ["[orphan] Node 'c' has no connections; connect it or remove it."]


# --- lint: each rule fires --------------------------------------------------------------------


def test_size():
    nodes = [(f"n{i}", "service") for i in range(31)]
    edges = [(f"n{i}", f"n{i + 1}", "calls") for i in range(30)]
    assert "size" in codes(make(nodes, edges, type="architecture"))


def test_orphan_skipped_for_org_and_notes():
    assert "orphan" not in codes(make([("a", "executive"), ("b", "position")], type="org"))
    spec = clean_arch()
    spec = spec.model_copy(update={"nodes": [*spec.nodes, *make([("n", "note")]).nodes]})
    assert "orphan" not in codes(spec)


def test_orphans_combined():
    spec = make([("a", "service"), ("b", "service"), ("c", "service"), ("d", "service")], [("a", "b", "x")],
                type="architecture")
    msg = next(f for f in lint.lint(norm(spec)) if f.startswith("[orphan]"))
    assert "'c', 'd'" in msg


def test_decision_needs_two_labeled_branches():
    one = make([("s", "start"), ("d", "decision"), ("e", "end")], [("s", "d"), ("d", "e", "yes")], type="flowchart")
    assert "decision" in codes(one)
    unlabeled = make([("s", "start"), ("d", "decision"), ("a", "process"), ("e", "end")],
                     [("s", "d"), ("d", "a"), ("d", "e", "no"), ("a", "e")], type="flowchart")
    assert "decision" in codes(unlabeled)


def test_flowchart_without_start_or_end():
    spec = make([("a", "process"), ("b", "process")], [("a", "b")], type="flowchart")
    msg = next(f for f in lint.lint(norm(spec)) if f.startswith("[terminal]"))
    assert "start or end" in msg


def test_state_without_initial():
    spec = make([("a", "state"), ("b", "state")], [("a", "b", "go")], type="state")
    assert "terminal" in codes(spec)


def test_state_events():
    spec = make([("i", "initial"), ("a", "state"), ("b", "state"), ("f", "final")],
                [("i", "a"), ("a", "b"), ("b", "f")], type="state")
    msgs = [f for f in lint.lint(norm(spec)) if f.startswith("[state-events]")]
    assert len(msgs) == 1 and "'a->b'" in msgs[0] and "i->a" not in msgs[0] and "b->f" not in msgs[0]


def test_label_length():
    spec = clean_arch()
    spec.nodes[1].label = "the web app that customers use daily"
    assert "label-length" in codes(spec)


def test_duplicate_label():
    spec = make([("a", "service", {"label": "Worker"}), ("b", "service", {"label": "worker"})],
                [("a", "b", "calls")], type="architecture")
    assert "duplicate-label" in codes(spec)
    ends = make([("s", "start"), ("d", "decision"), ("e1", "end", {"label": "Done"}),
                 ("e2", "end", {"label": "Done"})], [("s", "d"), ("d", "e1", "yes"), ("d", "e2", "no")],
                type="flowchart")
    assert "duplicate-label" not in codes(ends)


def test_edge_labels_mostly_missing():
    spec = make([("a", "webapp"), ("b", "api"), ("c", "database"), ("d", "queue")],
                [("a", "b"), ("b", "c"), ("b", "d", "publishes")], type="architecture")
    assert "edge-labels" in codes(spec)
    spec_flow = make([("a", "process"), ("b", "process"), ("c", "process"), ("d", "process")],
                     [("a", "b"), ("b", "c"), ("c", "d")], type="pipeline")
    assert "edge-labels" not in codes(spec_flow)


def test_mixed_providers():
    spec = make([("a", "aws-lambda"), ("b", "azure-functions")], [("a", "b", "HTTPS")], type="cloud")
    assert "mixed-providers" in codes(spec)
    multi = make([("a", "aws-lambda", {"group": "aws"}), ("b", "azure-functions", {"group": "az"})],
                 [("a", "b", "HTTPS")], [{"id": "aws", "kind": "cloud"}, {"id": "az", "kind": "cloud"}],
                 type="cloud")
    assert "mixed-providers" not in codes(multi)


def test_cloud_without_provider_kinds():
    spec = make([("a", "service"), ("b", "database")], [("a", "b", "SQL")], type="cloud")
    assert "provider-kinds" in codes(spec)


def test_unknown_kind():
    assert "unknown-kind" in codes(make([("a", "frobnicator"), ("b", "service")], [("a", "b", "x")]))


def test_single_member_group():
    spec = make([("a", "service", {"group": "g"}), ("b", "service")], [("a", "b", "calls")],
                [{"id": "g", "kind": "generic"}], type="architecture")
    assert "single-member" in codes(spec)
    subnet = make([("a", "service", {"group": "g"}), ("b", "service")], [("a", "b", "calls")],
                  [{"id": "g", "kind": "subnet"}], type="architecture")
    assert "single-member" not in codes(subnet)


def test_nesting_depth_and_order():
    groups = [{"id": "g0", "kind": "cloud"}] + [
        {"id": f"g{i}", "kind": "generic", "parent": f"g{i - 1}"} for i in range(1, 6)]
    spec = make([("a", "service", {"group": "g5"}), ("b", "service")], [("a", "b", "calls")], groups,
                type="architecture")
    assert "nesting" in codes(spec)
    inverted = make([("a", "service", {"group": "r"}), ("b", "service")], [("a", "b", "calls")],
                    [{"id": "s", "kind": "subnet"}, {"id": "r", "kind": "region", "parent": "s"}],
                    type="architecture")
    assert "nesting-order" in codes(inverted)


def test_emphasis_overuse():
    spec = make([(n, "service", {"emphasis": True}) for n in "abc"], [("a", "b", "x"), ("b", "c", "y")],
                type="architecture")
    assert "emphasis" in codes(spec)


def test_bidirectional_overuse():
    spec = make([(n, "service") for n in "abcd"],
                [{"source": "a", "target": "b", "label": "x", "arrow": "both"},
                 {"source": "b", "target": "c", "label": "x", "arrow": "both"},
                 ("c", "d", "x"), ("d", "c", "y")], type="architecture")
    assert "bidirectional" in codes(spec)


def test_erd_cardinality():
    spec = make([("a", "entity"), ("b", "entity")], [("a", "b", "has")], type="erd")
    assert "erd-cardinality" in codes(spec)
    ok = make([("a", "entity"), ("b", "entity")], [("a", "b", "1..*")], type="erd")
    assert "erd-cardinality" not in codes(ok)


def test_swimlane_nodes_outside_lanes():
    spec = make([("s", "start", {"group": "l"}), ("a", "process"), ("e", "end", {"group": "l"})],
                [("s", "a"), ("a", "e")], [{"id": "l", "kind": "lane"}], type="swimlane")
    found = lint.findings(norm(spec))
    assert found[0].code == "lane" and found[0].severity == "high"
    no_lanes = make([("s", "start"), ("e", "end")], [("s", "e")], type="swimlane")
    assert "lane" in codes(no_lanes)


def test_custom_colors():
    fills = ["#111111", "#222222", "#333333", "#444444"]
    spec = make([(f"n{i}", "service", {"fill": f}) for i, f in enumerate(fills)],
                [(f"n{i}", f"n{i + 1}", "x") for i in range(3)], type="architecture")
    assert "colors" in codes(spec)


def test_external_inside_internal_group():
    spec = make([("a", "service", {"group": "sys"}), ("x", "external", {"group": "sys"})], [("a", "x", "calls")],
                [{"id": "sys", "kind": "system"}], type="architecture")
    assert "external-placement" in codes(spec)
    ok = make([("a", "service", {"group": "sys"}), ("x", "external", {"group": "ext"})], [("a", "x", "calls")],
              [{"id": "sys", "kind": "system"}, {"id": "ext", "kind": "external"}], type="architecture")
    assert "external-placement" not in codes(ok)


def test_c4_context_with_containers():
    spec = make([("u", "person"), ("s", "system"), ("db", "database")], [("u", "s", "uses"), ("s", "db", "reads")],
                type="c4-context")
    assert "c4-context" in codes(spec)


def test_layout_mismatch():
    spec = make([("a", "process", {"group": "l"})], groups=[{"id": "l", "kind": "lane"}], type="swimlane",
                layout="flowchart-tb")
    assert "layout" in codes(spec)


def test_title_and_subtitle():
    assert "title" in codes(clean_arch(title="Diagram"))
    assert "title" in codes(clean_arch(subtitle=""))


def test_self_loop_and_duplicate_edge():
    spec = make([("a", "service"), ("b", "service")], [("a", "a", "retry"), ("a", "b", "x"), ("a", "b", "x")],
                type="architecture")
    assert {"self-loop", "duplicate-edge"} <= set(codes(spec))


def test_edge_label_length():
    spec = clean_arch()
    spec.edges[0].label = "sends a very long request"
    assert "edge-label-length" in codes(spec)


# --- ordering and capping ---------------------------------------------------------------------


def test_findings_ordered_by_severity_and_deterministic():
    spec = make([("d", "decision"), ("x", "service")] + [(f"n{i}", "service", {"emphasis": True}) for i in range(31)],
                type="flowchart", title="Diagram")
    a = lint.lint(norm(spec))
    assert a == lint.lint(norm(spec))
    found = lint.findings(norm(spec))
    ranks = [lint.SEVERITY_RANK[f.severity] for f in found]
    assert ranks == sorted(ranks)
    assert found[0].code == "size"


def test_findings_capped():
    nodes = []
    edges = []
    for i in range(20):  # 20 decisions with one branch each -> 20 high findings
        nodes += [(f"d{i}", "decision"), (f"p{i}", "process")]
        edges.append((f"d{i}", f"p{i}", "yes"))
    out = lint.lint(norm(make(nodes, edges, type="flowchart")))
    assert len(out) == lint.MAX_FINDINGS
    assert out[-1].startswith("[more]")


def test_every_rule_code_is_documented():
    assert len(set(lint.RULE_CODES)) == len(lint.RULE_CODES)
