"""Drawer: draw specs to files, live in Visio desktop when it is installed, natively otherwise.

Drawer is what the CLI and the MCP server use. With Visio it opens the app (or attaches to
the user's running Visio) and builds the diagram shape by shape in front of them, then saves
and exports through Visio. Without Visio it writes a native .vsdx plus SVG/PNG/HTML previews
(native.py).

Visio work must stay on one thread (COM apartment): the server uses com_thread, the CLI
calls from its main thread.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from visio_mcp.output import native
from visio_mcp.output.detect import visio_available
from visio_mcp.output.files import default_out_dir, open_file, save_free, slug
from visio_mcp.output.native import Progress
from visio_mcp.output.result import DrawOutput
from visio_mcp.output.visio.backend import VisioBackend
from visio_mcp.output.visio.draw import emit_visio
from visio_mcp.output.visio.edit import apply_ops
from visio_mcp.output.visio.inspect import inspect
from visio_mcp.plan import build_plan
from visio_mcp.spec import DiagramSpec, PatchOp, RenderResult
from visio_mcp.spec.edit import apply_to_spec

# default_out_dir, open_file, slug and visio_available are re-exported for the cli/mcp call sites
__all__ = ["DrawOutput", "Drawer", "default_out_dir", "open_file", "slug", "visio_available"]

Target = Literal["auto", "visio", "native"]


class Drawer:
    """Renders, patches, opens and exports one diagram at a time, in Visio or natively."""

    def __init__(
        self,
        target: Target = "auto",
        live: bool = True,
        attach: bool = False,
        live_delay: float = 0.06,
        backend: VisioBackend | None = None,
    ) -> None:
        if target == "visio" and backend is None and not visio_available():
            raise RuntimeError("Microsoft Visio desktop is not installed here; use target 'native'")
        self.target: Literal["visio", "native"] = (
            "visio" if backend is not None or (target != "native" and visio_available()) else "native"
        )
        self.live, self.attach, self.live_delay = live, attach, live_delay
        self._backend = backend
        self.spec: DiagramSpec | None = None  # spec of the open diagram, when drawn by us
        self.vsdx: Path | None = None  # file of the open diagram
        self.formats: list[str] = ["png"]

    def render(
        self, spec: DiagramSpec, vsdx: str | Path, formats: list[str] | None = None,
        progress: Progress | None = None,
    ) -> DrawOutput:
        """Draw a whole diagram and save it (plus previews) next to vsdx."""
        formats = list(formats if formats is not None else self.formats)
        self.spec, self.vsdx, self.formats = None, None, formats  # a failed render leaves nothing to patch
        out = self._draw(spec, Path(vsdx), formats, progress)
        self.spec, self.vsdx = spec, out.vsdx
        return out

    def patch(self, ops: list[PatchOp], formats: list[str] | None = None,
              progress: Progress | None = None) -> DrawOutput:
        """Edit the open diagram. Spec-drawn diagrams are re-rendered; opened files edited in place."""
        if self.vsdx is None:
            raise ValueError("no diagram open: call render_diagram or open_diagram first")
        formats = list(formats if formats is not None else self.formats)
        if self.spec is None:
            result = apply_ops(self.backend(), ops)
            return self._save(result, self.vsdx, formats)
        spec, moves, warnings = apply_to_spec(self.spec, ops)
        out = self._draw(spec, self.vsdx, formats, progress, after=moves)
        out.result.warnings[:0] = warnings
        self.spec, self.vsdx = spec, out.vsdx
        return out

    def open(self, path: str | Path) -> dict:
        """Open an existing .vsdx/.vsd in Visio for shape-by-shape patching; returns its inspection."""
        p = Path(path).expanduser().resolve()
        if p.suffix.lower() not in (".vsdx", ".vsd") or not p.is_file():
            raise ValueError(f"not an existing .vsdx/.vsd file: {p}")
        if self.target != "visio":
            raise RuntimeError("opening existing diagrams needs Microsoft Visio desktop")
        self.spec, self.vsdx = None, None
        self.backend().open_document(str(p))
        self.vsdx = p
        return inspect(self.backend())

    def inspect(self) -> dict:
        if self.target == "visio" and self._backend is not None:
            return inspect(self.backend())
        if self.spec is None:
            raise ValueError("no diagram open")
        return native.inspect_plan(build_plan(self.spec))

    def export(self, fmt: str, path: str | Path | None = None) -> Path:
        """Export the open diagram as fmt, to path or next to its .vsdx."""
        if path:
            target = Path(path).with_suffix(f".{fmt}")
        elif self.vsdx:
            target = self.vsdx.with_suffix(f".{fmt}")
        else:
            raise ValueError("no diagram open")
        if self.target == "visio":
            return Path(self.backend().export(str(target)))
        if self.spec is None:
            raise ValueError("no diagram open")
        files = native.previews(build_plan(self.spec), target, [fmt])
        if fmt not in files:
            raise RuntimeError(f"could not export {fmt} without Visio (no renderer available)")
        return files[fmt]

    def backend(self) -> VisioBackend:
        """The Visio backend, started on first use (Visio target only)."""
        if self._backend is None:
            from visio_mcp.output.visio.com import VisioCom

            self._backend = VisioCom(
                visible=self.live or self.attach,
                live_delay=self.live_delay if self.live else 0.0,
                attach=self.attach,
            )
        return self._backend

    def close(self) -> None:
        close = getattr(self._backend, "close", None)
        if close:
            close()
        self._backend = None

    def _draw(self, spec: DiagramSpec, vsdx: Path, formats: list[str], progress: Progress | None,
              after: list[PatchOp] | None = None) -> DrawOutput:
        if self.target == "native":
            return native.render(spec, vsdx, formats, progress)
        say = progress or (lambda _m: None)
        say("Planning layout")
        backend = self.backend()
        plan = build_plan(spec, backend.has_master)
        result = emit_visio(backend, plan, say)
        if after:
            result = result.model_copy(update={"warnings": result.warnings + apply_ops(backend, after).warnings})
        say("Saving")
        out = self._save(result, vsdx, formats)
        out.plan = plan
        return out

    def _save(self, result: RenderResult, vsdx: Path, formats: list[str]) -> DrawOutput:
        """Save through Visio and export the previews it can make (html is native-only)."""
        backend = self.backend()
        saved, warning = save_free(lambda p: Path(backend.save(str(p))), vsdx)
        previews = {f: Path(backend.export(str(saved.with_suffix(f".{f}")))) for f in formats if f != "html"}
        warnings = result.warnings + ([warning] if warning else [])
        files = [str(saved)] + [str(p) for p in previews.values()]
        self.vsdx = saved
        return DrawOutput(result.model_copy(update={"files": files, "warnings": warnings}), saved, "visio",
                          previews=previews)
