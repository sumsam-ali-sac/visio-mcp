"""build_plan: normalized spec in, positioned and styled elements out."""

from __future__ import annotations

from visio_mcp.plan import DiagramPlan, build_plan
from visio_mcp.spec import DiagramSpec


def _spec(**extra) -> DiagramSpec:
    return DiagramSpec.model_validate({
        "title": "Orders",
        "nodes": [{"id": "api", "label": "orders api", "kind": "service"},
                  {"id": "db", "label": "orders db", "kind": "database"}],
        "edges": [{"source": "api", "target": "db", "label": "Reads From"}],
        **extra,
    })


def test_plan_has_every_element_inside_the_page():
    plan = build_plan(_spec())
    assert isinstance(plan, DiagramPlan)
    assert [n.id for n in plan.nodes] == ["api", "db"] and len(plan.edges) == 1
    for n in plan.nodes:
        assert 0 <= n.rect.left and n.rect.right <= plan.width
        assert 0 <= n.rect.bottom and n.rect.top <= plan.height


def test_labels_are_cased_and_edges_named():
    plan = build_plan(_spec())
    assert plan.node("api").label == "Orders API"
    assert plan.edges[0].name == "api->db" and plan.edges[0].label == "reads from"
    assert len(plan.edges[0].points) >= 2


def test_title_block_and_theme_background():
    plan = build_plan(_spec(subtitle="v1"))
    assert plan.title is not None and plan.title.runs[0].text == "Orders"
    assert plan.theme.name == "professional"


def test_no_title_means_no_title_block():
    spec = _spec()
    plan = build_plan(spec.model_copy(update={"title": ""}))
    assert plan.title is None


def test_groups_wrap_their_members():
    plan = build_plan(_spec(
        groups=[{"id": "g", "label": "Backend"}],
        nodes=[{"id": "api", "label": "Api", "group": "g"}, {"id": "db", "label": "Db", "group": "g"}]))
    g = plan.groups[0]
    assert g.members == ["api", "db"] and g.depth == 0 and g.parent is None
    for n in plan.nodes:
        assert g.rect.left <= n.rect.left and n.rect.right <= g.rect.right


def test_empty_group_is_skipped_with_warning():
    plan = build_plan(_spec(groups=[{"id": "empty", "label": "Nothing"}]))
    assert not plan.groups and any("empty" in w for w in plan.warnings)


def test_legend_needs_at_least_two_entries():
    plan = build_plan(_spec(legend=True))
    assert plan.legend is not None and len(plan.legend_entries) >= 2
    single = build_plan(DiagramSpec.model_validate({"legend": True, "nodes": [{"id": "a", "label": "A"}]}))
    assert single.legend is None


def test_emphasis_and_fill_override_style():
    plan = build_plan(DiagramSpec.model_validate({
        "nodes": [{"id": "a", "label": "A", "fill": "#123456", "emphasis": True}]}))
    n = plan.node("a")
    assert n.style.fill == "#123456" and n.style.line == plan.theme.accent and n.style.line_weight >= 2.0
