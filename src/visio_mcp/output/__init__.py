"""Drawing outputs and the Drawer that picks one.

    drawer.py   Drawer: render/patch/open/export, live in Visio or natively
    native.py   no-Visio rendering: .vsdx + SVG/PNG/HTML/PDF previews
    result.py   DrawOutput returned by every render
    files.py    file naming, output folder, opening files, locked-file fallback
    detect.py   is Visio desktop installed?
    visio/      Visio desktop over COM (VisioBackend, VisioCom, draw, edit, inspect)
    vsdx/       native .vsdx writer
    svg/        SVG, HTML viewer and PNG previews
"""
