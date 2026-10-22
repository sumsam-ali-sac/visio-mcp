"""Drawing in Microsoft Visio desktop over COM.

    backend.py     VisioBackend protocol (what draw/edit need), ShapeInfo, TextRun
    draw.py        draw a DiagramPlan through a backend
    edit.py        patch shapes of a drawing opened from disk
    inspect.py     read the page back: shapes, connectors, overlaps
    com_thread.py  run every COM call on one thread
    com.py         VisioCom: the backend over COM, composing the modules below
      app.py, errors.py, document.py, stencils.py, page.py, names.py,
      shapes.py, connectors.py, containers.py, text.py, formatting.py, cells.py
"""
