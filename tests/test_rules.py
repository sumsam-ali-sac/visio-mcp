import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from visio_mcp import lint, rules
from visio_mcp.spec import DiagramSpec

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "src" / "visio_mcp" / "rules"
EXPECTED_FILES = {"general", *rules.TYPES, "cloud-azure", "cloud-aws", "cloud-gcp"}


def test_types_match_spec():
    assert "auto" not in rules.TYPES
    assert len(rules.TYPES) == 14
    assert {"flowchart", "cloud", "c4-context", "erd", "mindmap"} <= set(rules.TYPES)


def test_rules_files_present():
    assert {p.stem for p in RULES_DIR.glob("*.md")} == EXPECTED_FILES


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
def test_every_rules_file_loads(name):
    text = rules._read(name)
    assert text.startswith("# ")
    assert 40 <= len(text.splitlines()) <= 170


def test_general():
    text = rules.general()
    for topic in ("Naming", "Flow direction", "Grouping", "Color", "Edge", "legend", "Split"):
        assert topic.lower() in text.lower()


def test_every_lint_code_documented():
    text = rules.general()
    for code in lint.RULE_CODES:
        assert f"[{code}]" in text, code


@pytest.mark.parametrize("dtype", rules.TYPES)
def test_type_file_sections(dtype):
    text = rules.type_rules(dtype)
    for section in ("## Checklist", "## Common mistakes", "## Example"):
        assert section in text


@pytest.mark.parametrize("dtype", rules.TYPES)
def test_example_validates_and_is_clean(dtype):
    spec = DiagramSpec.model_validate(rules.example(dtype))
    assert spec.type == dtype
    normalized, _ = lint.normalize(spec)
    found = lint.findings(normalized)
    assert not [f for f in found if f.severity == "high"], found
    assert found == [], found  # examples should be exemplary


@pytest.mark.parametrize("dtype", rules.TYPES)
def test_example_type_is_inferred(dtype):
    spec = DiagramSpec.model_validate(rules.example(dtype) | {"type": "auto"})
    assert lint.normalize(spec)[0].type == dtype


@pytest.mark.parametrize("dtype", rules.TYPES)
def test_example_kinds_known(dtype):
    spec = DiagramSpec.model_validate(rules.example(dtype))
    unknown = [n.kind for n in spec.nodes if not lint.kind_info(n.kind).known]
    assert not unknown


def test_type_summary():
    summary = rules.type_summary()
    assert list(summary) == list(rules.TYPES)
    assert all(line and "\n" not in line for line in summary.values())


def test_get_rules_composition():
    flow = rules.get_rules("flowchart")
    assert flow.startswith(rules.general().strip())
    assert rules.type_rules("flowchart").strip() in flow
    assert "Amazon Web Services" not in flow

    cloud = rules.get_rules("cloud")
    for p in ("Microsoft Azure", "Amazon Web Services", "Google Cloud conventions"):
        assert p in cloud

    aws = rules.get_rules("cloud", provider="aws")
    assert "Amazon Web Services" in aws and "Microsoft Azure conventions" not in aws

    arch = rules.get_rules("architecture", provider="Google")
    assert "Google Cloud conventions" in arch


def test_get_rules_errors():
    with pytest.raises(ValueError, match="flowchart"):
        rules.get_rules("sequence")
    with pytest.raises(ValueError):
        rules.get_rules("auto")
    with pytest.raises(ValueError, match="azure"):
        rules.get_rules("cloud", provider="oracle")
    with pytest.raises(ValueError):
        rules.example("nope")


def test_provider_files_use_known_kinds():
    for p in rules.PROVIDERS:
        text = rules.provider_rules(p)
        prefix = {"azure": "azure-", "aws": "aws-", "gcp": "gcp-"}[p]
        kinds = set(re.findall(rf"`({prefix}[a-z0-9-]+)`", text))
        assert kinds
        unknown = sorted(k for k in kinds if not lint.kind_info(k).known)
        assert not unknown, unknown


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_wheel_includes_rules(tmp_path):
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)],
                   check=True, capture_output=True, timeout=300)
    wheel = next(tmp_path.glob("*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for name in EXPECTED_FILES:
        assert f"visio_mcp/rules/{name}.md" in names
    assert "visio_mcp/rules.py" in names
