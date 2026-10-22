"""Draw specs to files: live in Visio desktop when it is installed, natively otherwise.

Drawer is what the CLI and the MCP server use. With Visio it opens the app (or attaches to
the user's running Visio) and builds the diagram shape by shape in front of them, then saves
and exports through Visio. Without Visio it writes a native .vsdx plus SVG/PNG/HTML previews.

Visio work must stay on one thread (COM apartment): the server uses com_thread, the CLI
calls from its main thread.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from visio_mcp import edit, render
from visio_mcp.backend import VisioBackend
from visio_mcp.plan import DiagramPlan, build_plan
from visio_mcp.spec import DiagramSpec, PatchOp, RenderResult

Target = Literal["auto", "visio", "native"]
Progress = Callable[[str], None]
NATIVE_FORMATS = ("png", "svg", "html", "pdf")


def visio_available() -> bool:
    """True on Windows when Visio desktop is registered for automation."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Visio.Application\CLSID"))
        return True
    except OSError:
        return False


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "diagram"


def default_out_dir() -> Path:
    d = Path(os.environ.get("VISIO_MCP_OUT") or Path.home() / "Documents" / "visio-mcp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_file(path: str | Path) -> None:
    """Open a file with the OS default app (Visio for .vsdx, browser for .html)."""
    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@dataclass
class DrawOutput:
    result: RenderResult
    vsdx: Path | None
    target: Literal["visio", "native"]
    plan: DiagramPlan | None = None
    previews: dict[str, Path] = field(default_factory=dict)  # format -> file

    @property
    def png(self) -> Path | None:
        return self.previews.get("png")


class Drawer:
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

    # --- public -----------------------------------------------------------------------------

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
            result = edit.apply_ops(self.backend(), ops)
            return self._save(result, self.vsdx, formats)
        spec, moves, warnings = edit.apply_to_spec(self.spec, ops)
        out = self._draw(spec, self.vsdx, formats, progress, after=moves)
        out.result.warnings[:0] = warnings
        self.spec, self.vsdx = spec, out.vsdx
        return out

    def open(self, path: str | Path) -> dict:
        p = Path(path).expanduser().resolve()
        if p.suffix.lower() not in (".vsdx", ".vsd") or not p.is_file():
            raise ValueError(f"not an existing .vsdx/.vsd file: {p}")
        if self.target != "visio":
            raise RuntimeError("opening existing diagrams needs Microsoft Visio desktop")
        self.spec, self.vsdx = None, None
        self.backend().open_document(str(p))
        self.vsdx = p
        return edit.inspect(self.backend())

    def inspect(self) -> dict:
        if self.target == "visio" and self._backend is not None:
            return edit.inspect(self.backend())
        if self.spec is None:
            raise ValueError("no diagram open")
        plan = build_plan(self.spec)
        return {
            "shapes": [{"id": n.id, "text": n.label, "kind": n.kind, "x": round(n.shape.x, 2),
                        "y": round(n.shape.y, 2), "width": n.shape.w, "height": n.shape.h} for n in plan.nodes],
            "groups": [{"id": g.id, "label": g.label, "members": g.members} for g in plan.groups],
            "connectors": [{"id": e.name, "source": e.source, "target": e.target, "label": e.label}
                           for e in plan.edges],
            "overlaps": _plan_overlaps(plan),
        }

    def export(self, fmt: str, path: str | Path | None = None) -> Path:
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
        files = _native_previews(build_plan(self.spec), target, [fmt])
        if fmt not in files:
            raise RuntimeError(f"could not export {fmt} without Visio (no renderer available)")
        return files[fmt]

    def backend(self) -> VisioBackend:
        """The Visio backend, started on first use (Visio target only)."""
        if self._backend is None:
            from visio_mcp.visio_com import VisioCom

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

    # --- internals ----------------------------------------------------------------------------

    def _draw(self, spec: DiagramSpec, vsdx: Path, formats: list[str], progress: Progress | None,
              after: list | None = None) -> DrawOutput:
        if self.target == "native":
            return _draw_native(spec, vsdx, formats, progress)
        say = progress or (lambda _m: None)
        say("Planning layout")
        backend = self.backend()
        plan = build_plan(spec, backend.has_master)
        result = render.emit_visio(backend, plan, say)
        if after:
            result = result.model_copy(update={"warnings": result.warnings + (edit.apply_ops(backend, after).warnings)})
        say("Saving")
        out = self._save(result, vsdx, formats)
        out.plan = plan
        return out

    def _save(self, result: RenderResult, vsdx: Path, formats: list[str]) -> DrawOutput:
        backend = self.backend()
        saved, warning = _save_free(backend, vsdx)
        previews = {f: Path(backend.export(str(saved.with_suffix(f".{f}")))) for f in formats if f != "html"}
        warnings = result.warnings + ([warning] if warning else [])
        files = [str(saved)] + [str(p) for p in previews.values()]
        self.vsdx = saved
        return DrawOutput(result.model_copy(update={"files": files, "warnings": warnings}), saved, "visio",
                          previews=previews)


def _save_free(backend: VisioBackend, vsdx: Path) -> tuple[Path, str | None]:
    """Save, or save under a free name when the file is open elsewhere (e.g. in Visio)."""
    try:
        return Path(backend.save(str(vsdx))), None
    except PermissionError:
        alt = _free_name(vsdx)
        backend.save(str(alt))
        return alt, f"{vsdx.name} is open in another program; saved as {alt.name}"


def _free_name(p: Path) -> Path:
    n = 2
    while (alt := p.with_name(f"{p.stem}-{n}{p.suffix}")).exists():
        n += 1
    return alt


def _draw_native(spec: DiagramSpec, vsdx: Path, formats: list[str], progress: Progress | None) -> DrawOutput:
    from visio_mcp.vsdx_writer import write_vsdx

    say = progress or (lambda _m: None)
    say("Planning layout")
    plan = build_plan(spec)
    say("Writing .vsdx")
    vsdx.parent.mkdir(parents=True, exist_ok=True)
    warning = None
    try:
        saved = write_vsdx(plan, vsdx)
    except PermissionError:
        alt = _free_name(vsdx)
        saved = write_vsdx(plan, alt)
        warning = f"{vsdx.name} is open in another program; saved as {alt.name}"
    say("Rendering previews")
    previews = _native_previews(plan, saved, formats)
    warnings = list(plan.warnings) + ([warning] if warning else [])
    missing = [f for f in formats if f not in previews]
    if missing:
        warnings.append(f"no renderer for {', '.join(missing)} on this machine; skipped")
    result = RenderResult(
        shapes=len(plan.nodes) + len(plan.groups), connectors=len(plan.edges), warnings=warnings,
        suggestions=plan.suggestions, overlaps=_plan_overlaps(plan),
        files=[str(saved)] + [str(p) for p in previews.values()],
    )
    return DrawOutput(result, Path(saved), "native", plan, previews)


def _native_previews(plan: DiagramPlan, base: Path, formats: list[str]) -> dict[str, Path]:
    from visio_mcp import svg

    out: dict[str, Path] = {}
    wanted = set(formats)
    svg_path = base.with_suffix(".svg")
    if wanted & {"svg", "png", "pdf"}:
        svg_path.write_text(svg.render_svg(plan), encoding="utf-8")
        if "svg" in wanted:
            out["svg"] = svg_path
    if "png" in wanted:
        png = svg.svg_to_png(svg_path, base.with_suffix(".png")) or _soffice_convert(base.with_suffix(".vsdx"), "png")
        if png:
            out["png"] = Path(png)
    if "pdf" in wanted and (pdf := _soffice_convert(base.with_suffix(".vsdx"), "pdf")):
        out["pdf"] = pdf
    if "html" in wanted:
        out["html"] = Path(svg.write_html(plan, base.with_suffix(".html")))
    if "svg" not in wanted and svg_path.exists() and "svg" not in out:
        svg_path.unlink(missing_ok=True)
    return out


def _soffice_convert(vsdx: Path, fmt: str) -> Path | None:
    """PDF without Visio via LibreOffice, when it is installed."""
    import shutil

    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe or not vsdx.exists():
        return None
    try:
        subprocess.run([exe, "--headless", "--convert-to", fmt, "--outdir", str(vsdx.parent), str(vsdx)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    out = vsdx.with_suffix(f".{fmt}")
    return out if out.exists() else None


def _plan_overlaps(plan: DiagramPlan) -> list[tuple[str, str]]:
    from visio_mcp.backend import ShapeInfo

    return render.find_overlaps([
        ShapeInfo(n.id, n.label, None, n.rect.x, n.rect.y, n.rect.w, n.rect.h) for n in plan.nodes
    ])
