
from visio_mcp import catalog, style
from visio_mcp.catalog.cloud import CLOUD_KINDS
from visio_mcp.catalog.generic import GENERIC_KINDS
from visio_mcp.catalog.stencils import BASFLO, FILLABLE

CANONICAL = ["process", "decision", "start", "end", "data", "document", "database", "service", "api", "webapp", "cache", "queue", "storage", "function", "gateway", "loadbalancer", "external", "user", "client", "mobile", "server", "router", "switch", "firewall", "cloud", "internet", "pc", "executive", "manager", "position", "entity", "box", "ellipse", "note", "component", "container", "system", "person", "external-system", "actor", "cron", "worker", "microservice", "topic", "search", "data-warehouse", "data-lake", "etl", "ml-model", "llm", "vector-db", "identity", "secrets", "monitoring", "logging", "cdn", "dns", "vpn", "waf", "registry", "repo", "pipeline", "build", "test", "deploy", "artifact", "email", "notification", "payment", "state", "initial", "final", "mindmap-root"]


def _all(stencil: str, master: str) -> bool:
    return True


def _none(stencil: str, master: str) -> bool:
    return False


def _generic():
    return {n: k for n, k in catalog.kinds().items() if not k.provider}


def _cloud():
    return {n: k for n, k in catalog.kinds().items() if k.provider}


def test_canonical_kinds_present():
    assert set(CANONICAL) <= set(catalog.kinds())


def test_every_kind_is_well_formed():
    for name, k in catalog.kinds().items():
        assert k.name == name
        assert k.description.strip()
        assert len(k.candidates) <= 3
        assert k.category in style.CATEGORIES, name
        assert k.geometry in style.GEOMETRY_MIN, name
        if not k.provider:
            assert k.candidates, name


def test_names_unique_and_lowercase():
    names = [k.name for k in GENERIC_KINDS + CLOUD_KINDS]
    assert len(names) == len(set(names))
    assert all(n == n.lower() and " " not in n for n in names)


def test_generic_kinds_resolve_to_clean_geometry():
    for n in ("service", "api", "webapp", "function", "gateway", "external", "queue", "cache", "storage",
              "database", "decision", "start", "document", "box"):
        r = catalog.resolve(n, _all)
        assert r.shape.stencil in FILLABLE, n
        assert not r.icon, n


def test_icon_flag_for_icon_masters():
    r = catalog.resolve("firewall", _all)
    assert r.shape.stencil not in FILLABLE
    assert r.icon
    assert not catalog.resolve("process", _all).icon


def test_aliases_point_at_real_kinds():
    for alias, target in catalog.ALIASES.items():
        assert target in catalog.kinds(), alias
        assert alias not in catalog.kinds() or alias == target, alias


def test_cloud_kinds():
    cloud = _cloud()
    assert set(catalog.providers()) == {"aws", "azure", "gcp"}
    for p in catalog.providers():
        assert sum(k.provider == p for k in cloud.values()) >= 25
    for name, k in cloud.items():
        assert name.startswith(f"{k.provider}-")
        assert k.base and k.glyph and k.geometry == "icon", name


def test_base_chains_terminate_in_generic_kind():
    kinds = catalog.kinds()
    for name, k in kinds.items():
        seen, cur = {name}, k
        while cur.base:
            assert cur.base in kinds and cur.base not in seen, name
            seen.add(cur.base)
            cur = kinds[cur.base]
        assert cur.provider is None, name


def test_first_available_candidate_wins():
    k = catalog.kinds()["database"]
    r = catalog.resolve("database", _all)
    assert r.shape == k.candidates[0]
    assert r.warning is None and r.kind is k


def test_skips_unavailable_candidates():
    k = catalog.kinds()["database"]
    second = k.candidates[1]
    r = catalog.resolve("database", lambda s, m: (s, m) == (second.stencil, second.master))
    assert r.shape == second
    assert r.warning is None


def test_fallback_with_warning_when_nothing_available():
    r = catalog.resolve("firewall", _none)
    assert r.shape == catalog.FALLBACK
    assert r.warning and "firewall" in r.warning


def test_cloud_kind_uses_provider_master_when_available():
    k = catalog.kinds()["azure-redis"]
    r = catalog.resolve("azure-redis", _all)
    assert r.shape == k.candidates[0] and r.icon and r.kind is k and r.warning is None


def test_cloud_kind_falls_back_to_base_silently():
    k = catalog.kinds()["aws-rds"]
    r = catalog.resolve("aws-rds", lambda s, m: s == BASFLO)
    assert r.shape == catalog.Shape(BASFLO, "Database")
    assert r.kind is k and k.provider == "aws" and k.glyph  # original kind kept
    assert r.warning is None and not r.icon
    # no provider candidates at all (GCP) -> base shape, still no warning
    g = catalog.resolve("gcp-pubsub", _all)
    assert g.kind.name == "gcp-pubsub" and g.warning is None
    assert g.shape == catalog.resolve("topic", _all).shape


def test_cloud_kind_nothing_available_warns():
    r = catalog.resolve("gcp-bigquery", _none)
    assert r.shape == catalog.FALLBACK and r.warning


def test_unknown_kind_warns_with_hint():
    r = catalog.resolve("flux-capacitor", _all)
    assert r.shape == catalog.FALLBACK
    assert r.kind is None
    assert r.warning and "flux-capacitor" in r.warning and "unknown" in r.warning
    r = catalog.resolve("databse", _all)
    assert r.kind is None and "did you mean" in r.warning and "database" in r.warning
    r = catalog.resolve("aws-lamb", _all)
    assert "aws-lambda" in r.warning


def test_lookup_is_exact():
    assert catalog.lookup(" DB ").name == "database"
    assert catalog.lookup("databse") is None


def test_case_insensitive_and_aliases():
    assert catalog.resolve("  SERVICE ", _all) == catalog.resolve("service", _all)
    assert catalog.resolve("DB", _all) == catalog.resolve("database", _all)
    assert catalog.resolve("postgres", _all) == catalog.resolve("database", _all)
    assert catalog.resolve("redis", _all) == catalog.resolve("cache", _all)
    assert catalog.resolve("kafka", _all) == catalog.resolve("topic", _all)
    assert catalog.resolve("rabbitmq", _all) == catalog.resolve("queue", _all)
    assert catalog.resolve("s3", _all) == catalog.resolve("aws-s3", _all)
    assert catalog.resolve("lambda", _all) == catalog.resolve("function", _all)
    assert catalog.resolve("terminator", _all) == catalog.resolve("start", _all)
    assert catalog.resolve("laptop", _all) == catalog.resolve("pc", _all)


def test_person_kinds_use_person_geometry():
    for n in ("user", "person", "actor"):
        k = catalog.kinds()[n]
        assert k.geometry == "person" and k.category == "person"


def test_kinds_by_category_and_describe():
    by_cat = catalog.kinds_by_category()
    assert set(by_cat) <= set(style.CATEGORIES)
    assert sum(len(v) for v in by_cat.values()) == len(_generic())
    text = catalog.describe_kinds()
    assert "`database`" in text and "`aws-s3`" in text and "`azure-redis`" in text and "`gcp-bigquery`" in text
    only = catalog.describe_kinds("aws")
    assert "`aws-s3`" in only and "`azure-redis`" not in only and "`gcp-bigquery`" not in only
    assert "`database`" in only
