"""End-to-end check against real Visio: draw every example live, patch, inspect, export.

    uv run python scripts/smoke.py            # live, in a visible Visio window
    uv run python scripts/smoke.py --hidden   # hidden Visio, faster

Output goes to diagrams/smoke/. Needs Windows with Visio desktop.
"""

import json
import sys
import time
from pathlib import Path

from pydantic import TypeAdapter

from visio_mcp.output.drawer import Drawer
from visio_mcp.spec import DiagramSpec, PatchOp

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "diagrams" / "smoke"


def main() -> None:
    drawer = Drawer(target="visio", live="--hidden" not in sys.argv)
    try:
        for f in sorted((ROOT / "examples").glob("*.json")):
            spec = DiagramSpec.model_validate_json(f.read_text(encoding="utf-8"))
            t = time.time()
            r = drawer.render(spec, OUT / f"{f.stem}.vsdx", ["png"]).result
            print(f"{f.stem}: {time.time() - t:.1f}s shapes={r.shapes} connectors={r.connectors} "
                  f"overlaps={r.overlaps} warnings={r.warnings}")

        first = spec.nodes[0].id
        ops = TypeAdapter(list[PatchOp]).validate_python([
            {"op": "update_node", "id": first, "label": "Patched", "emphasis": True},
            {"op": "remove", "id": "does-not-exist"},
            {"op": "update_diagram", "theme": "blueprint", "layout": "flowchart-lr"},
        ])
        print("patch:", drawer.patch(ops).result.model_dump_json(indent=1))
        found = drawer.inspect()
        print(f"inspect: {len(found['shapes'])} shapes, {len(found['connectors'])} connectors, "
              f"overlaps={found['overlaps']}")
        print("pdf:", drawer.export("pdf"))
        print(json.dumps({"ok": True}))
    finally:
        drawer.close()


if __name__ == "__main__":
    main()
