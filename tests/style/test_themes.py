"""Theme registry and completeness."""

from __future__ import annotations

import pytest

from visio_mcp.style import CATEGORIES, PROFESSIONAL, THEMES, get_theme


def test_registry_holds_every_named_theme():
    assert set(THEMES) == {"professional", "azure", "aws", "gcp", "c4", "blueprint", "dark", "monochrome"}
    assert all(t.name == k for k, t in THEMES.items())


@pytest.mark.parametrize("alias,name", [
    ("default", "professional"), ("light", "professional"), ("mono", "monochrome"),
    ("google", "gcp"), ("  AWS ", "aws"),
])
def test_get_theme_resolves_aliases_and_case(alias, name):
    assert get_theme(alias).name == name


def test_get_theme_unknown_lists_choices():
    with pytest.raises(ValueError, match="unknown theme 'nope'.*professional"):
        get_theme("nope")


@pytest.mark.parametrize("name", sorted(THEMES))
def test_every_theme_styles_every_category_and_group_kind(name):
    theme = THEMES[name]
    assert all(c in theme.nodes for c in CATEGORIES)
    assert theme.node_style("unheard-of") is theme.nodes["generic"]
    assert theme.group_style("unheard-of") is theme.groups["generic"]
    assert theme.group_style("boundary").header.bold


def test_dark_themes_are_flagged():
    assert get_theme("dark").dark and get_theme("blueprint").dark and not PROFESSIONAL.dark
