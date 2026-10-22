import re

from visio_mcp import catalog

CANONICAL = (
    "process decision start end data document database service api webapp cache queue storage "
    "function gateway loadbalancer external user client mobile server router switch firewall "
    "cloud internet pc executive manager position entity box ellipse note"
).split()


def _all(stencil: str, master: str) -> bool:
    return True


def _none(stencil: str, master: str) -> bool:
    return False


def test_canonical_kinds_present():
    assert set(CANONICAL) <= set(catalog.kinds())


def test_every_kind_is_well_formed():
    for name, k in catalog.kinds().items():
        assert k.name == name
        assert k.description.strip()
        assert 1 <= len(k.candidates) <= 3
        assert k.fill is None or re.fullmatch(r"#[0-9A-Fa-f]{6}", k.fill)


def test_first_available_candidate_wins():
    k = catalog.kinds()["database"]
    r = catalog.resolve("database", _all)
    assert r.shape == k.candidates[0]
    assert r.fill == k.fill
    assert r.warning is None


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


def test_unknown_kind_warns():
    r = catalog.resolve("flux-capacitor", _all)
    assert r.shape == catalog.FALLBACK
    assert r.fill is None
    assert r.warning and "flux-capacitor" in r.warning and "unknown" in r.warning


def test_case_insensitive_and_aliases():
    assert catalog.resolve("  SERVICE ", _all) == catalog.resolve("service", _all)
    assert catalog.resolve("DB", _all) == catalog.resolve("database", _all)
    assert catalog.resolve("actor", _all) == catalog.resolve("user", _all)
    assert catalog.resolve("person", _all) == catalog.resolve("user", _all)
    assert catalog.resolve("terminator", _all) == catalog.resolve("start", _all)
    assert catalog.resolve("laptop", _all) == catalog.resolve("pc", _all)


def test_aliases_point_at_real_kinds():
    for alias, target in catalog._ALIASES.items():
        assert target in catalog.kinds(), alias
