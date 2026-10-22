"""write_html: a single-file viewer with the inline SVG, pan/zoom, light/dark chrome and SVG download."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

from visio_mcp.output.svg.render import render_svg
from visio_mcp.plan import DiagramPlan

_HTML = """<!doctype html>
<html lang="en" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#F4F5F7;--panel:#FFFFFF;--ink:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#2563EB;--dot:#D5DAE1;--shadow:0 1px 2px rgba(15,23,42,.08),0 12px 32px rgba(15,23,42,.10)}
:root[data-theme=dark]{--bg:#0B1020;--panel:#141B2D;--ink:#E5E9F2;--muted:#8B97AD;--line:#26304A;--accent:#60A5FA;--dot:#1C2540;--shadow:0 1px 2px rgba(0,0,0,.5),0 16px 40px rgba(0,0,0,.45)}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.4 'Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif;display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--line);flex:none}
h1{font-size:15px;font-weight:600;margin:0;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
h1 small{font-weight:400;color:var(--muted);margin-left:10px;font-size:12.5px}
.tools{display:flex;gap:6px;align-items:center}
button{font:inherit;color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:8px;height:32px;min-width:32px;padding:0 10px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px}
button:hover{background:color-mix(in srgb,var(--accent) 10%,transparent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#zoom{min-width:48px;text-align:center;color:var(--muted);font-variant-numeric:tabular-nums;font-size:12.5px}
#vp{flex:1;position:relative;overflow:hidden;cursor:grab;touch-action:none;background-image:radial-gradient(var(--dot) 1px,transparent 1px);background-size:22px 22px}
#vp.drag{cursor:grabbing}
#canvas{position:absolute;left:0;top:0;transform-origin:0 0;box-shadow:var(--shadow);border-radius:4px;overflow:hidden;line-height:0;user-select:none;-webkit-user-select:none}
#canvas svg{display:block}
footer{position:absolute;left:16px;bottom:12px;color:var(--muted);font-size:12px;pointer-events:none}
@media(max-width:560px){h1 small,.lbl{display:none}}
</style>
</head>
<body>
<header>
  <h1>__TITLE__<small>__SUB__</small></h1>
  <div class="tools">
    <button id="out" title="Zoom out (-)" aria-label="Zoom out">&minus;</button>
    <span id="zoom">100%</span>
    <button id="in" title="Zoom in (+)" aria-label="Zoom in">+</button>
    <button id="fit" title="Fit to window (0)">Fit</button>
    <button id="theme" title="Toggle light/dark interface" aria-label="Toggle theme">&#9680;</button>
    <button id="dl" title="Download SVG">&#8681;<span class="lbl">SVG</span></button>
  </div>
</header>
<div id="vp"><div id="canvas">__SVG__</div><footer>Scroll to zoom &middot; drag to pan &middot; 0 fit &middot; + / &minus; zoom</footer></div>
<script>
(function(){
var vp=document.getElementById('vp'),cv=document.getElementById('canvas'),svg=cv.querySelector('svg');
var W=parseFloat(svg.getAttribute('width')),H=parseFloat(svg.getAttribute('height'));
var s=1,x=0,y=0,fitted=true,MIN=.05,MAX=10;
function apply(){cv.style.transform='translate('+x+'px,'+y+'px) scale('+s+')';document.getElementById('zoom').textContent=Math.round(s*100)+'%';}
function fit(){var vw=vp.clientWidth,vh=vp.clientHeight,pad=40;s=Math.min((vw-pad)/W,(vh-pad)/H,2);s=Math.max(s,MIN);x=(vw-W*s)/2;y=(vh-H*s)/2;fitted=true;apply();}
function zoomAt(cx,cy,f){var n=Math.min(MAX,Math.max(MIN,s*f));f=n/s;x=cx-(cx-x)*f;y=cy-(cy-y)*f;s=n;fitted=false;apply();}
function center(f){zoomAt(vp.clientWidth/2,vp.clientHeight/2,f);}
vp.addEventListener('wheel',function(e){e.preventDefault();var r=vp.getBoundingClientRect();var k=e.ctrlKey?.01:.0016;zoomAt(e.clientX-r.left,e.clientY-r.top,Math.exp(-e.deltaY*k));},{passive:false});
var drag=null;
vp.addEventListener('pointerdown',function(e){if(e.button!==0)return;drag={px:e.clientX,py:e.clientY,x:x,y:y};vp.classList.add('drag');vp.setPointerCapture(e.pointerId);});
vp.addEventListener('pointermove',function(e){if(!drag)return;x=drag.x+e.clientX-drag.px;y=drag.y+e.clientY-drag.py;fitted=false;apply();});
function end(e){drag=null;vp.classList.remove('drag');}
vp.addEventListener('pointerup',end);vp.addEventListener('pointercancel',end);
vp.addEventListener('dblclick',fit);
document.getElementById('in').onclick=function(){center(1.25)};
document.getElementById('out').onclick=function(){center(1/1.25)};
document.getElementById('fit').onclick=fit;
document.addEventListener('keydown',function(e){if(e.metaKey||e.ctrlKey||e.altKey)return;
 if(e.key==='0')fit();else if(e.key==='+'||e.key==='=')center(1.25);else if(e.key==='-'||e.key==='_')center(1/1.25);});
window.addEventListener('resize',function(){if(fitted)fit();});
var root=document.documentElement;
document.getElementById('theme').onclick=function(){root.setAttribute('data-theme',root.getAttribute('data-theme')==='dark'?'light':'dark');};
document.getElementById('dl').onclick=function(){
 var src='<?xml version="1.0" encoding="UTF-8"?>\\n'+new XMLSerializer().serializeToString(svg);
 var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([src],{type:'image/svg+xml'}));
 a.download=__FILENAME__;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(a.href)},1000);};
fit();
})();
</script>
</body>
</html>
"""


def write_html(plan: DiagramPlan, path: str | os.PathLike) -> Path:
    """Write a self-contained HTML viewer (inline SVG, pan/zoom, chrome theme toggle, SVG download)."""
    svg = render_svg(plan)
    title = plan.spec.title or "Diagram"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-").lower() or "diagram"
    sub = f"{len(plan.nodes)} nodes · {len(plan.edges)} connections"
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    page = (_HTML.replace("__THEME__", "dark" if plan.theme.dark else "light")
            .replace("__TITLE__", html.escape(title))
            .replace("__SUB__", html.escape(sub))
            .replace("__FILENAME__", json.dumps(slug + ".svg").replace("</", "<\\/"))
            .replace("__SVG__", svg))
    out.write_text(page, encoding="utf-8")
    return out
