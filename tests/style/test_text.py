"""Label casing, text width and wrapping."""

from __future__ import annotations

import pytest

from visio_mcp.style import sentence_case, text_width, title_case, wrap


@pytest.mark.parametrize("raw,expected", [
    ("user login service", "User Login Service"),
    ("api gateway for the web", "API Gateway for the Web"),
    ("postgresql database", "PostgreSQL Database"),
    ("the end", "The End"),
    ("build v2 pipeline", "Build v2 Pipeline"),
    ("read-only cache", "Read-Only Cache"),
    ("camelCase stays", "camelCase Stays"),
    ("(optional) step", "(Optional) Step"),
])
def test_title_case(raw, expected):
    assert title_case(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Reads From", "reads from"),
    ("HTTPS", "HTTPS"),
    ("Yes", "yes"),
    ("calls API v2", "calls API v2"),
])
def test_sentence_case(raw, expected):
    assert sentence_case(raw) == expected


def test_text_width_grows_with_length_size_and_bold():
    assert text_width("", 10) == 0
    assert text_width("abcdef", 10) > text_width("abc", 10)
    assert text_width("abc", 20) > text_width("abc", 10)
    assert text_width("abc", 10, bold=True) > text_width("abc", 10)
    assert text_width("iii", 10) < text_width("abc", 10) < text_width("MWM", 10)


def test_wrap_respects_width_and_never_returns_nothing():
    lines = wrap("one two three four five six", 10, 0.8)
    assert len(lines) > 1 and " ".join(lines) == "one two three four five six"
    assert all(text_width(line, 10) <= 0.8 or " " not in line for line in lines)
    assert wrap("", 10, 1.0) == [""]
    assert wrap("unbreakableword", 10, 0.1) == ["unbreakableword"]
