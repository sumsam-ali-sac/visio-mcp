"""The OPC package parts of a .vsdx: content types, relationships, properties, document, pages, windows."""

from __future__ import annotations

from datetime import datetime, timezone
from xml.sax.saxutils import escape

from visio_mcp.output.vsdx.cells import ARROW_FILLED, ARROW_SIZE, attrs, cell, clean, length, num, points
from visio_mcp.output.vsdx.page import STYLE_CONNECTOR, STYLE_NONE, STYLE_NORMAL, STYLE_TEXT, Page
from visio_mcp.plan import DiagramPlan

NS = "http://schemas.microsoft.com/office/visio/2012/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"

REL_DOCUMENT = "http://schemas.microsoft.com/visio/2010/relationships/document"
REL_PAGES = "http://schemas.microsoft.com/visio/2010/relationships/pages"
REL_PAGE = "http://schemas.microsoft.com/visio/2010/relationships/page"
REL_WINDOWS = "http://schemas.microsoft.com/visio/2010/relationships/windows"
REL_CORE = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
REL_APP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

CT_DOCUMENT = "application/vnd.ms-visio.drawing.main+xml"
CT_PAGES = "application/vnd.ms-visio.pages+xml"
CT_PAGE = "application/vnd.ms-visio.page+xml"
CT_WINDOWS = "application/vnd.ms-visio.windows+xml"
CT_CORE = "application/vnd.openxmlformats-package.core-properties+xml"
CT_APP = "application/vnd.openxmlformats-officedocument.extended-properties+xml"
CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_PNG = "image/png"

_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

_COLORS = ["#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
           "#800000", "#008000", "#000080", "#808000", "#800080", "#008080", "#C0C0C0", "#E6E6E6",
           "#CDCDCD", "#B3B3B3", "#9A9A9A", "#808080", "#666666", "#4D4D4D", "#333333", "#1A1A1A"]


def parts(plan: DiagramPlan, page: Page) -> dict[str, str]:
    """Every XML part of the package by part name (media files are added by the writer)."""
    out = {
        "[Content_Types].xml": content_types(images=bool(page.media)),
        "_rels/.rels": rels([
            ("rId1", REL_DOCUMENT, "visio/document.xml"),
            ("rId2", REL_CORE, "docProps/core.xml"),
            ("rId3", REL_APP, "docProps/app.xml"),
        ]),
        "docProps/app.xml": app_xml(),
        "docProps/core.xml": core_xml(plan.spec.title or "Diagram"),
        "visio/document.xml": document_xml(page.fonts),
        "visio/_rels/document.xml.rels": rels([
            ("rId1", REL_PAGES, "pages/pages.xml"),
            ("rId2", REL_WINDOWS, "windows.xml"),
        ]),
        "visio/windows.xml": windows_xml(plan),
        "visio/pages/pages.xml": pages_xml(plan),
        "visio/pages/_rels/pages.xml.rels": rels([("rId1", REL_PAGE, "page1.xml")]),
        "visio/pages/page1.xml": page_xml(page),
    }
    if page.media:
        out["visio/pages/_rels/page1.xml.rels"] = rels(
            [(rid, REL_IMAGE, f"../media/{part}") for rid, part in page.media.values()])
    return out


def page_xml(page: Page) -> str:
    connects = f"<Connects>{''.join(page.connects)}</Connects>" if page.connects else ""
    return (f'{_XML}<PageContents xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">'
            f"<Shapes>{''.join(s.xml() for s in page.shapes)}</Shapes>{connects}</PageContents>")


def pages_xml(plan: DiagramPlan) -> str:
    w, h = plan.width, plan.height
    sheet = "".join([
        length("PageWidth", w), length("PageHeight", h),
        length("ShdwOffsetX", 0.125), length("ShdwOffsetY", -0.125),
        cell("PageScale", 1.0, "IN_F"), cell("DrawingScale", 1.0, "IN_F"),
        cell("DrawingSizeType", 3),  # custom size
        cell("DrawingScaleType", 0),
        cell("InhibitSnap", 0), cell("PageLockReplace", 0, "BOOL"), cell("PageLockDuplicate", 0, "BOOL"),
        cell("UIVisibility", 0), cell("ShdwType", 0), cell("ShdwObliqueAngle", 0.0),
        cell("ShdwScaleFactor", 1.0), cell("DrawingResizeType", 2),  # keep our size
        cell("PageShapeSplit", 1),
        cell("PrintPageOrientation", 2 if w > h else 1),
        cell("LineJumpCode", 0),  # no line jumps on this page
        cell("RouteStyle", 1),
        length("PageLeftMargin", 0.25), length("PageRightMargin", 0.25),
        length("PageTopMargin", 0.25), length("PageBottomMargin", 0.25),
    ])
    page = (f'<Page{attrs(ID=0, NameU="Page-1", Name="Page-1", ViewScale=-1, ViewCenterX=num(w / 2), ViewCenterY=num(h / 2))}>'
            f'<PageSheet LineStyle="0" FillStyle="0" TextStyle="0">{sheet}</PageSheet>'
            f'<Rel r:id="rId1"/></Page>')
    return f'{_XML}<Pages xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">{page}</Pages>'


def _style_sheet(sid: int, name: str, parent: int | None, cells: list[str], sections: str = "") -> str:
    p = "" if parent is None else attrs(LineStyle=parent, FillStyle=parent, TextStyle=parent)
    return f'<StyleSheet{attrs(ID=sid, NameU=name, IsCustomNameU=1, Name=name, IsCustomName=1)}{p}>{"".join(cells)}{sections}</StyleSheet>'


def document_xml(fonts: list[str]) -> str:
    """Document settings, color table, face names and the four style sheets shapes inherit from."""
    base_font = fonts[0] if fonts else "Calibri"
    no_style = [
        cell("EnableLineProps", 1), cell("EnableFillProps", 1), cell("EnableTextProps", 1),
        cell("HideForApply", 0),
        points("LineWeight", 0.75), cell("LineColor", "#000000"), cell("LinePattern", 1),
        length("Rounding", 0.0), cell("EndArrowSize", 2), cell("BeginArrow", 0), cell("EndArrow", 0),
        cell("LineCap", 0), cell("BeginArrowSize", 2), cell("LineColorTrans", 0), cell("CompoundType", 0),
        cell("FillForegnd", "#FFFFFF"), cell("FillBkgnd", "#000000"), cell("FillPattern", 1),
        cell("ShdwForegnd", "#000000"), cell("ShdwPattern", 0), cell("FillForegndTrans", 0),
        cell("FillBkgndTrans", 0), cell("ShdwForegndTrans", 0), cell("ShapeShdwType", 0),
        length("ShapeShdwOffsetX", 0.0), length("ShapeShdwOffsetY", 0.0), cell("ShapeShdwObliqueAngle", 0.0),
        cell("ShapeShdwScaleFactor", 1.0), cell("ShapeShdwBlur", 0.0), cell("ShapeShdwShow", 0),
        points("LeftMargin", 0), points("RightMargin", 0), points("TopMargin", 0), points("BottomMargin", 0),
        cell("VerticalAlign", 1), length("DefaultTabStop", 0.5),
        cell("TextDirection", 0),
        cell("LockTextEdit", 0), cell("LockVtxEdit", 0), cell("LockCalcWH", 0),
    ]
    char = ('<Section N="Character"><Row IX="0">' + cell("Font", base_font) + cell("Color", "#000000")
            + cell("Style", 0) + cell("Case", 0) + cell("Pos", 0) + cell("FontScale", 1) + points("Size", 12)
            + cell("ColorTrans", 0) + "</Row></Section>")
    para = ('<Section N="Paragraph"><Row IX="0">' + cell("IndFirst", 0.0) + cell("IndLeft", 0.0)
            + cell("IndRight", 0.0) + cell("SpLine", -1.2) + cell("SpBefore", 0.0) + cell("SpAfter", 0.0)
            + cell("HorzAlign", 1) + cell("Bullet", 0) + "</Row></Section>")
    normal = [points("LeftMargin", 4), points("RightMargin", 4), points("TopMargin", 4), points("BottomMargin", 4),
              points("LineWeight", 1), cell("LineColor", "#94A3B8")]
    connector = [cell("EndArrow", ARROW_FILLED), cell("EndArrowSize", ARROW_SIZE), cell("FillPattern", 0),
                 points("LineWeight", 1.25), cell("LineColor", "#64748B")]
    text_only = [cell("LinePattern", 0), cell("FillPattern", 0), points("LeftMargin", 0), points("RightMargin", 0),
                 points("TopMargin", 0), points("BottomMargin", 0)]
    sheets = "".join([
        _style_sheet(STYLE_NONE, "No Style", None, no_style, char + para),
        _style_sheet(STYLE_NORMAL, "Normal", STYLE_NONE, normal),
        _style_sheet(STYLE_CONNECTOR, "Connector", STYLE_NORMAL, connector),
        _style_sheet(STYLE_TEXT, "Text Only", STYLE_NORMAL, text_only),
    ])
    colors = "".join(f'<ColorEntry IX="{i}" RGB="{c}"/>' for i, c in enumerate(_COLORS))
    faces = "".join(f"<FaceName{attrs(NameU=f)}/>" for f in (fonts or ["Calibri"]))
    settings = (f'<DocumentSettings TopPage="0" DefaultTextStyle="{STYLE_NORMAL}" DefaultLineStyle="{STYLE_NORMAL}" '
                f'DefaultFillStyle="{STYLE_NORMAL}" DefaultGuideStyle="{STYLE_NONE}">'
                "<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions>"
                "<SnapAngles/><DynamicGridEnabled>1</DynamicGridEnabled><ProtectStyles>0</ProtectStyles>"
                "<ProtectShapes>0</ProtectShapes><ProtectMasters>0</ProtectMasters><ProtectBkgnds>0</ProtectBkgnds>"
                "</DocumentSettings>")
    doc_sheet = ('<DocumentSheet NameU="TheDoc" IsCustomNameU="1" Name="TheDoc" IsCustomName="1" '
                 'LineStyle="0" FillStyle="0" TextStyle="0">'
                 + cell("OutputFormat", 0) + cell("LockPreview", 0) + cell("AddMarkup", 0)
                 + cell("ViewMarkup", 0) + cell("DocLockReplace", 0, "BOOL") + cell("NoCoauth", 0, "BOOL")
                 + cell("DocLockDuplicatePage", 0, "BOOL") + cell("PreviewQuality", 0)
                 + cell("PreviewScope", 0) + cell("DocLangID", 1033) + "</DocumentSheet>")
    return (f'{_XML}<VisioDocument xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">'
            f"{settings}<Colors>{colors}</Colors><FaceNames>{faces}</FaceNames>"
            f"<StyleSheets>{sheets}</StyleSheets>{doc_sheet}</VisioDocument>")


def windows_xml(plan: DiagramPlan) -> str:
    win = (f'<Window{attrs(ID=0, WindowType="Drawing", WindowState=1073741824, WindowLeft=-8, WindowTop=-31, WindowWidth=1600, WindowHeight=900, ContainerType="Page", Page=0, ViewScale=-1, ViewCenterX=num(plan.width / 2), ViewCenterY=num(plan.height / 2))}>'
           "<ShowRulers>1</ShowRulers><ShowGrid>0</ShowGrid><ShowPageBreaks>0</ShowPageBreaks>"
           "<ShowGuides>1</ShowGuides><ShowConnectionPoints>1</ShowConnectionPoints>"
           "<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions>"
           "<SnapAngles/><DynamicGridEnabled>1</DynamicGridEnabled><TabSplitterPos>0.5</TabSplitterPos>"
           "</Window>")
    return f'{_XML}<Windows ClientWidth="1600" ClientHeight="900" xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">{win}</Windows>'


def rels(items: list[tuple[str, str, str]]) -> str:
    body = "".join(f"<Relationship{attrs(Id=i, Type=t, Target=tg)}/>" for i, t, tg in items)
    return f'{_XML}<Relationships xmlns="{NS_PKG_REL}">{body}</Relationships>'


def content_types(images: bool = False) -> str:
    overrides = [
        ("/visio/document.xml", CT_DOCUMENT),
        ("/visio/pages/pages.xml", CT_PAGES),
        ("/visio/pages/page1.xml", CT_PAGE),
        ("/visio/windows.xml", CT_WINDOWS),
        ("/docProps/core.xml", CT_CORE),
        ("/docProps/app.xml", CT_APP),
    ]
    body = (f'<Default Extension="rels" ContentType="{CT_RELS}"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + (f'<Default Extension="png" ContentType="{CT_PNG}"/>' if images else "")
            + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in overrides))
    return f'{_XML}<Types xmlns="{NS_CT}">{body}</Types>'


def core_xml(title: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f'{_XML}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(clean(title))}</dc:title><dc:creator>visio-mcp</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            "</cp:coreProperties>")


def app_xml() -> str:
    return (f'{_XML}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            "<Application>visio-mcp</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
            "<HeadingPairs><vt:vector size=\"2\" baseType=\"variant\"><vt:variant><vt:lpstr>Pages</vt:lpstr></vt:variant>"
            "<vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>"
            "<TitlesOfParts><vt:vector size=\"1\" baseType=\"lpstr\"><vt:lpstr>Page-1</vt:lpstr></vt:vector></TitlesOfParts>"
            "<Company></Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>"
            "<HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion></Properties>")
