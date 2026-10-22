"""Diagram ground rules in code: normalize a spec (resolve 'auto', fix casing) and lint it.

`normalize` makes the mechanical fixes nobody should have to ask for. `lint` reports the
judgment calls back to the agent as short, actionable one-liners, each prefixed with a
rule code (``[orphan] Node 'cache' has no connections; ...``). The prose behind every
rule lives in ``visio_mcp/rules/*.md`` (see ``visio_mcp.rules``).
"""

from visio_mcp.lint.finding import RULE_CODES, SEVERITY_RANK, Finding
from visio_mcp.lint.infer import LAYOUTS
from visio_mcp.lint.kinds import KindInfo, kind_info
from visio_mcp.lint.normalize import normalize
from visio_mcp.lint.report import MAX_FINDINGS, findings, lint

__all__ = [
    "LAYOUTS", "MAX_FINDINGS", "RULE_CODES", "SEVERITY_RANK", "Finding", "KindInfo", "findings", "kind_info",
    "lint", "normalize",
]
