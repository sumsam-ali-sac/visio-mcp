"""DiagramPlan -> native .vsdx file, no Visio needed (Mac, Linux, CI).

Writes a Visio 2013+ OPC package ([MS-VSDX]) by hand with the standard library:

    [Content_Types].xml
    _rels/.rels
    docProps/app.xml, docProps/core.xml
    visio/document.xml               style sheets, face names, colors
    visio/_rels/document.xml.rels
    visio/windows.xml
    visio/pages/pages.xml            one page, sized to the plan
    visio/pages/_rels/pages.xml.rels
    visio/pages/page1.xml            shapes + connects
    visio/pages/_rels/page1.xml.rels icons (only when the plan has images)
    visio/media/imageN.png           official cloud icons / custom icons, as Foreign shapes

No masters: every shape carries its own Geometry sections, so the file opens the same
everywhere. Nodes, groups and connectors are named like the COM backend names them
(node id, group id, 'source->target'), and connectors are glued to their nodes with
dynamic glue so they stay attached when shapes move in Visio.

Coordinates in the plan already match Visio's: inches, origin bottom-left, center pins.
"""

from visio_mcp.output.vsdx.writer import write_vsdx

__all__ = ["write_vsdx"]
