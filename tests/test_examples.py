from pathlib import Path

import pytest

from visio_mcp.mcp import guide as prompts
from visio_mcp.spec import DiagramSpec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))


def test_examples_exist():
    assert len(EXAMPLES) >= 10


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_is_valid_spec(path: Path):
    spec = DiagramSpec.model_validate_json(path.read_text(encoding="utf-8"))
    assert spec.nodes


@pytest.mark.parametrize("source", ["prompt", "repo"])
def test_diagram_prompt_mentions_subject(source: str):
    text = prompts.diagram_prompt("payments-service", source=source)  # type: ignore[arg-type]
    assert text.strip()
    assert "payments-service" in text


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_follows_the_rules(path: Path):
    from visio_mcp import lint

    spec, _ = lint.normalize(DiagramSpec.model_validate_json(path.read_text(encoding="utf-8")))
    high = [f for f in lint.findings(spec) if f.severity == "high"]
    assert high == []


def test_guide_mentions_tools():
    assert "render_diagram" in prompts.GUIDE
    assert "patch_diagram" in prompts.GUIDE
    assert "get_diagram_rules" in prompts.GUIDE
