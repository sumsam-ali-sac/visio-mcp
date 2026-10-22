"""End-to-end check against real Visio: render every example, patch, inspect, export.

    uv run python scripts/smoke.py

Output goes to diagrams/smoke/.
"""

import asyncio
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("VISIO_MCP_OUT", str(ROOT / "diagrams" / "smoke"))

from visio_mcp import com_thread, server  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

from visio_mcp.spec import DiagramSpec, PatchOp  # noqa: E402


async def main() -> None:
    spec = None
    for f in sorted((ROOT / "examples").glob("*.json")):
        spec = DiagramSpec.model_validate_json(f.read_text())
        t = time.time()
        out = await server.render_diagram(spec, name=f.stem, formats=["png"])
        r = json.loads(out[0])
        print(
            f"{f.stem}: {time.time() - t:.1f}s shapes={r['shapes']} connectors={r['connectors']} "
            f"overlaps={r['overlaps']} warnings={r['warnings']}"
        )

    first = spec.nodes[0].id
    ops = TypeAdapter(list[PatchOp]).validate_python(
        [
            {"op": "update_node", "id": first, "label": "Patched", "fill": "#FFD6D6"},
            {"op": "remove", "id": "does-not-exist"},
            {"op": "relayout", "layout": "flowchart-lr"},
        ]
    )
    out = await server.patch_diagram(ops)
    print("patch:", json.loads(out[0]))
    found = await server.inspect_diagram()
    print(f"inspect: {len(found['shapes'])} shapes, {len(found['connectors'])} connectors, overlaps={found['overlaps']}")
    print("pdf:", await server.export_diagram("pdf"))
    await com_thread.call(lambda: server.backend().close())


if __name__ == "__main__":
    asyncio.run(main())
