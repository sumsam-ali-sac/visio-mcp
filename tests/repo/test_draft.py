"""The no-AI fallback: heuristic DiagramSpec drafts."""

from __future__ import annotations

from pathlib import Path

import pytest

from visio_mcp import catalog
from visio_mcp.repo import discover, heuristic_spec, scan


@pytest.mark.parametrize("dtype", ["architecture", "cloud", "deployment", "pipeline", "erd", "c4-container", "mindmap"])
def test_heuristic_spec_valid_for_every_type(workspace: Path, bicep_repo: Path, dtype: str, assert_valid):
    repos = discover(workspace) + [scan(bicep_repo)]
    for subset in (repos, repos[:1], []):
        spec = heuristic_spec(subset, dtype)
        assert_valid(spec)
        assert spec.subtitle == "Generated from repository scan"


def test_architecture_spec_single_repo(fastapi_repo: Path, assert_valid):
    spec = heuristic_spec([scan(fastapi_repo)])
    assert spec.type == "architecture" and spec.title == "orders-api architecture"
    assert_valid(spec)
    nodes = {n.id: n for n in spec.nodes}
    labels = {n.label: n for n in spec.nodes}
    assert {"orders-api", "PostgreSQL", "Redis", "Stripe", "OpenAI", "Users"} <= set(labels)
    assert labels["PostgreSQL"].kind == "database" and labels["Redis"].kind in ("cache", "database")
    assert labels["Stripe"].kind == "external"
    groups = {g.id: g for g in spec.groups}
    assert {g.label for g in groups.values()} >= {"Clients", "Data", "External", "orders-api"}
    assert groups[labels["Stripe"].group].kind == "external"
    assert groups[labels["PostgreSQL"].group].label == "Data"
    pairs = {(nodes[e.source].label, nodes[e.target].label) for e in spec.edges}
    assert ("Users", "orders-api") in pairs
    assert ("orders-api", "PostgreSQL") in pairs and ("orders-api", "Redis") in pairs
    # compose: separate worker service depends on the stores
    assert ("worker", "PostgreSQL") in pairs and ("worker", "Redis") in pairs
    assert any(n.label == "Celery worker" for n in spec.nodes) is True


def test_architecture_spec_cloud_kinds(tf_repo: Path, bicep_repo: Path, assert_valid):
    spec = heuristic_spec([scan(tf_repo)], "cloud")
    assert_valid(spec)
    kinds = [n.kind for n in spec.nodes]
    # provider kinds only when the catalog knows them; otherwise base kinds
    expect_lambda = "aws-lambda" if catalog.lookup("aws-lambda") else "function"
    assert expect_lambda in kinds
    assert any(g.kind == "cloud" and g.label == "AWS" for g in spec.groups)
    assert spec.type == "cloud"
    pairs = {(e.source, e.target) for e in spec.edges}
    events = next(n.id for n in spec.nodes if n.label == "events")
    lam = next(n.id for n in spec.nodes if n.kind in ("aws-lambda", "function"))
    assert (lam, events) in pairs

    spec = heuristic_spec([scan(bicep_repo)], "architecture")
    assert_valid(spec)
    assert any(g.kind == "cloud" and g.label == "Azure" for g in spec.groups)
    assert len({n.id for n in spec.nodes}) == len(spec.nodes)
    expect_fn = "azure-functions" if catalog.lookup("azure-functions") else "function"
    assert expect_fn in {n.kind for n in spec.nodes}


def test_architecture_spec_multi_repo_links(workspace: Path, assert_valid):
    spec = heuristic_spec(discover(workspace))
    assert_valid(spec)
    labels = {n.label: n.id for n in spec.nodes}
    assert {"orders-api", "storefront"} <= set(labels)
    # the frontend reads the API's URL from config: a synchronous HTTPS call
    assert any(e.source == labels["storefront"] and e.target == labels["orders-api"] and e.label == "HTTPS"
               and e.style == "solid" for e in spec.edges)
    # repo frames are kept only when they hold more than one node
    for g in (g for g in spec.groups if g.kind == "system"):
        assert sum(1 for n in spec.nodes if n.group == g.id) >= 2
    assert spec.title == "ws architecture"


def test_pipeline_spec(fastapi_repo: Path, assert_valid):
    spec = heuristic_spec([scan(fastapi_repo)], "pipeline")
    assert spec.type == "pipeline" and spec.title == "orders-api pipeline"
    assert_valid(spec)
    by_label = {n.label: n for n in spec.nodes}
    ids = {n.label: n.id for n in spec.nodes}
    pairs = {(e.source, e.target) for e in spec.edges}
    assert (ids["test"], ids["build"]) in pairs and (ids["build"], ids["deploy"]) in pairs
    assert by_label["deploy"].emphasis
    assert any(e.label == "deploys" for e in spec.edges)


def test_pipeline_spec_without_ci_is_suggested(next_repo: Path, assert_valid):
    spec = heuristic_spec([scan(next_repo)], "pipeline")
    assert_valid(spec)
    assert {"Commit", "Build", "Deploy"} <= {n.label for n in spec.nodes}


def test_deployment_spec_compose(fastapi_repo: Path, assert_valid):
    spec = heuristic_spec([scan(fastapi_repo)], "deployment")
    assert spec.type == "deployment"
    assert_valid(spec)
    assert any(g.kind == "environment" and g.label == "Docker Compose" for g in spec.groups)
    ids = {n.label: n.id for n in spec.nodes}
    pairs = {(e.source, e.target) for e in spec.edges}
    assert (ids["api"], ids["db"]) in pairs and (ids["api"], ids["cache"]) in pairs
    assert ("internet" in {n.id for n in spec.nodes}) and (ids["Internet"], ids["api"]) in pairs


def test_unknown_kinds_fall_back(monkeypatch: pytest.MonkeyPatch, tf_repo: Path):
    real = catalog.lookup
    monkeypatch.setattr(catalog, "lookup", lambda k: None if k.startswith(("aws-", "dynamodb", "topic")) else real(k))
    spec = heuristic_spec([scan(tf_repo)], "cloud")
    assert not any(n.kind.startswith("aws-") for n in spec.nodes)
    assert any(n.kind == "function" for n in spec.nodes)
