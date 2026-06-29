"""
Construction Site Planner  ·  v3.0
─────────────────────────────────────────────────────────────────────────────
Features:
  • Shapes  – Rectangle, L-Shape, T-Shape, Hexagon, Circle, Semicircle,
               Road (polyline + width), Custom Polygon
  • Interactive HTML canvas – drag structures to move, drag corner handles
                              to resize, pan with middle-mouse or pan mode
  • Boundary editor – draw/drag vertices, freehand, smooth, pan/zoom
  • Safety clearance + boundary setback (configurable)
  • Snap-to-grid, rotation per structure
  • Space-utilisation panel
  • JSON export / import
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from shapely.affinity import rotate as sh_rotate
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Site Planner",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
section[data-testid="stSidebar"] { background: #1E2A38 !important; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small { color: #C5D4E3 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #FFFFFF !important; }
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #FFFFFF !important; font-size: 1.3rem !important; }
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] { color: #8BAACC !important; }
div[data-testid="stMetric"] {
    background: #F0F4FA; border-radius: 10px;
    padding: 10px 14px 8px; border-left: 4px solid #4A90D9; }
.block-container { padding-top: 1rem !important; }
div[data-testid="stHorizontalBlock"] button {
    border-radius: 8px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
CATEGORY_COLORS: dict[str, str] = {
    "Office / Admin":    "#4A90D9",
    "Warehouse":         "#E07B39",
    "Workshop / Lab":    "#6BBF59",
    "Storage Yard":      "#9B59B6",
    "Utility / Plant":   "#F1C40F",
    "Access Road":       "#7F8C8D",
    "Green / Landscape": "#27AE60",
    "Custom":            "#E74C3C",
}

SHAPE_TYPES = [
    "Rectangle", "L-Shape", "T-Shape",
    "Hexagon", "Circle", "Semicircle",
    "Road", "Custom Polygon",
]

DEFAULT_BOUNDARY: list[tuple[float, float]] = [
    (0, 0), (100, 0), (110, 35), (100, 80), (55, 85), (0, 60),
]

CIRCLE_SEGMENTS = 48


# ─────────────────────────────────────────────────────────────
# COLOUR UTILITIES
# ─────────────────────────────────────────────────────────────
def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ─────────────────────────────────────────────────────────────
# SESSION-STATE BOOTSTRAP
# ─────────────────────────────────────────────────────────────
def _init() -> None:
    defaults: dict = {
        "buildings":          {},
        "site_vertices":      list(DEFAULT_BOUNDARY),
        "safety_margin":      2.0,
        "boundary_threshold": 1.5,
        "selected_id":        None,
        "edit_mode":          "view",
        "show_safety_zones":  True,
        "show_utilisation":   True,
        "snap_grid":          1.0,
        # canvas ↔ streamlit sync
        "canvas_cmd":         "",   # JSON command string sent TO the canvas
        "canvas_event":       "",   # JSON event string received FROM the canvas
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init()


# ─────────────────────────────────────────────────────────────
# GEOMETRY HELPERS
# ─────────────────────────────────────────────────────────────
def _circle_pts(cx, cy, r, n=CIRCLE_SEGMENTS):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def make_rectangle(x, y, w, h, angle=0.0) -> Polygon:
    p = Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    return sh_rotate(p, angle, origin=(x + w / 2, y + h / 2))


def make_l_shape(x, y, w, h, sw, sh_, angle=0.0) -> Polygon:
    p = Polygon([(x, y), (x + w, y), (x + w, y + sh_),
                 (x + sw, y + sh_), (x + sw, y + h), (x, y + h)])
    return sh_rotate(p, angle, origin=(x + w / 2, y + h / 2))


def make_t_shape(x, y, w, h, cap_h, angle=0.0) -> Polygon:
    sw, sx = w / 3, x + w / 3
    top  = Polygon([(x, y), (x + w, y), (x + w, y + cap_h), (x, y + cap_h)])
    stem = Polygon([(sx, y + cap_h), (sx + sw, y + cap_h),
                    (sx + sw, y + h), (sx, y + h)])
    return sh_rotate(top.union(stem), angle, origin=(x + w / 2, y + h / 2))


def make_hexagon(cx, cy, r, angle=0.0) -> Polygon:
    pts = [(cx + r * math.cos(math.radians(60 * i)),
            cy + r * math.sin(math.radians(60 * i))) for i in range(6)]
    return sh_rotate(Polygon(pts), angle, origin=(cx, cy))


def make_circle(cx, cy, r) -> Polygon:
    return Polygon(_circle_pts(cx, cy, r))


def make_semicircle(cx, cy, r, flat_angle=0.0, angle=0.0) -> Polygon:
    n = CIRCLE_SEGMENTS // 2
    pts = [(cx, cy)]
    for i in range(n + 1):
        a = math.radians(flat_angle) + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return sh_rotate(Polygon(pts), angle, origin=(cx, cy))


def make_road(waypoints, width) -> Polygon:
    if len(waypoints) < 2:
        return Polygon()
    buf = LineString(waypoints).buffer(width / 2, cap_style=2, join_style=2)
    return buf if buf.geom_type == "Polygon" else buf.convex_hull


def building_polygon(b: dict) -> Polygon:
    s = b["shape"]
    x, y = float(b.get("x", 0)), float(b.get("y", 0))
    angle = float(b.get("angle", 0))
    try:
        if s == "Rectangle":
            return make_rectangle(x, y, b["width"], b["height"], angle)
        if s == "L-Shape":
            return make_l_shape(x, y, b["width"], b["height"],
                                b.get("stem_w", b["width"] / 2),
                                b.get("stem_h", b["height"] / 2), angle)
        if s == "T-Shape":
            return make_t_shape(x, y, b["width"], b["height"],
                                b.get("cap_h", b["height"] / 3), angle)
        if s == "Hexagon":
            return make_hexagon(x, y, b["radius"], angle)
        if s == "Circle":
            return make_circle(x, y, b["radius"])
        if s == "Semicircle":
            return make_semicircle(x, y, b["radius"],
                                   b.get("flat_angle", 0), angle)
        if s == "Road":
            wp = [tuple(p) for p in b.get("waypoints", [])]
            return make_road(wp, b.get("road_width", 5.0))
        if s == "Custom Polygon":
            pts = b.get("custom_pts", [])
            if len(pts) >= 3:
                raw = Polygon(pts)
                return sh_rotate(raw, angle, origin=raw.centroid)
    except Exception:
        pass
    return Polygon()


def site_polygon() -> Polygon:
    v = st.session_state.site_vertices
    return Polygon(v) if len(v) >= 3 else Polygon()


def snap(val: float, grid: float) -> float:
    return round(val / grid) * grid if grid > 0 else val


# ─────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────
def check_collisions(target_id: str, poly: Polygon) -> list[str]:
    m = st.session_state.safety_margin
    return [
        b["name"]
        for bid, b in st.session_state.buildings.items()
        if bid != target_id
        and not building_polygon(b).is_empty
        and poly.buffer(m / 2).intersects(building_polygon(b).buffer(m / 2))
    ]


def check_boundary(poly: Polygon) -> bool:
    site = site_polygon()
    if site.is_empty:
        return True
    inner = site.buffer(-st.session_state.boundary_threshold)
    return (not inner.is_empty
            and inner.geom_type in ("Polygon", "MultiPolygon")
            and inner.contains(poly))


# ─────────────────────────────────────────────────────────────
# UTILISATION STATS
# ─────────────────────────────────────────────────────────────
def utilisation_stats() -> dict:
    site = site_polygon()
    site_area = site.area if not site.is_empty else 0.0
    polys = [p for p in (building_polygon(b)
                         for b in st.session_state.buildings.values())
             if not p.is_empty]
    union = unary_union(polys) if polys else Polygon()
    inside = union.intersection(site).area if not site.is_empty else union.area
    return {
        "site_area":       site_area,
        "inside_area":     inside,
        "free_area":       max(0.0, site_area - inside),
        "utilisation_pct": (inside / site_area * 100) if site_area > 0 else 0.0,
        "n_buildings":     len(st.session_state.buildings),
    }


# ─────────────────────────────────────────────────────────────
# IMPORT / EXPORT
# ─────────────────────────────────────────────────────────────
def export_state() -> str:
    return json.dumps({
        "site_vertices":      st.session_state.site_vertices,
        "safety_margin":      st.session_state.safety_margin,
        "boundary_threshold": st.session_state.boundary_threshold,
        "buildings":          st.session_state.buildings,
    }, indent=2)


def import_state(raw: str) -> None:
    data = json.loads(raw)
    st.session_state.site_vertices      = [tuple(v) for v in data.get("site_vertices", DEFAULT_BOUNDARY)]
    st.session_state.safety_margin      = data.get("safety_margin", 2.0)
    st.session_state.boundary_threshold = data.get("boundary_threshold", 1.5)
    st.session_state.buildings          = data.get("buildings", {})


# ─────────────────────────────────────────────────────────────
# BUILD CANVAS STATE PAYLOAD  (sent to JS)
# ─────────────────────────────────────────────────────────────
def _build_canvas_payload() -> str:
    """Serialise everything the canvas needs to render."""
    buildings_list = []
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        pts: list[list[float]] = []
        if not poly.is_empty:
            xs, ys = poly.exterior.xy
            pts = [[float(x), float(y)] for x, y in zip(xs, ys)]
        buf_pts: list[list[float]] = []
        if not poly.is_empty and st.session_state.show_safety_zones:
            buf = poly.buffer(st.session_state.safety_margin)
            if buf.geom_type == "Polygon":
                bx, by = buf.exterior.xy
                buf_pts = [[float(x), float(y)] for x, y in zip(bx, by)]
        # bounding box for resize handles (axis-aligned, pre-rotation)
        bb = poly.bounds if not poly.is_empty else (0, 0, 0, 0)
        buildings_list.append({
            "id":       bid,
            "name":     b["name"],
            "color":    b.get("color", "#4A90D9"),
            "selected": bid == st.session_state.selected_id,
            "pts":      pts,
            "buf_pts":  buf_pts,
            "x":        float(b.get("x", 0)),
            "y":        float(b.get("y", 0)),
            "width":    float(b.get("width", b.get("radius", 10) * 2)),
            "height":   float(b.get("height", b.get("radius", 10) * 2)),
            "radius":   float(b.get("radius", 0)),
            "shape":    b["shape"],
            "angle":    float(b.get("angle", 0)),
            "bbox":     list(bb),
            "bnd_ok":   check_boundary(poly),
            "clr_ok":   not check_collisions(bid, poly),
        })

    site = site_polygon()
    site_pts: list[list[float]] = []
    setback_pts: list[list[float]] = []
    if not site.is_empty:
        sx, sy = site.exterior.xy
        site_pts = [[float(x), float(y)] for x, y in zip(sx, sy)]
        inner = site.buffer(-st.session_state.boundary_threshold)
        if not inner.is_empty and inner.geom_type in ("Polygon", "MultiPolygon"):
            g = inner if inner.geom_type == "Polygon" else list(inner.geoms)[0]
            ix, iy = g.exterior.xy
            setback_pts = [[float(x), float(y)] for x, y in zip(ix, iy)]

    return json.dumps({
        "buildings":      buildings_list,
        "site_pts":       site_pts,
        "setback_pts":    setback_pts,
        "bnd_verts":      list(st.session_state.site_vertices),
        "snap_grid":      st.session_state.snap_grid,
        "show_safety":    st.session_state.show_safety_zones,
        "edit_mode":      st.session_state.edit_mode,
        "selected_id":    st.session_state.selected_id,
    })


# ─────────────────────────────────────────────────────────────
# INTERACTIVE CANVAS  (one HTML component for everything)
# ─────────────────────────────────────────────────────────────
CANVAS_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: monospace; background: #F5F8FC; overflow: hidden; }
#toolbar {
  display: flex; gap: 6px; padding: 6px 8px; flex-wrap: wrap;
  background: #EEF2F7; border-bottom: 1px solid #CDD9E8;
  align-items: center;
}
button {
  padding: 4px 10px; border: none; border-radius: 5px;
  cursor: pointer; font-size: 11px; font-family: monospace; font-weight: 600;
}
.btn-blue   { background:#4A90D9; color:#fff; }
.btn-red    { background:#E74C3C; color:#fff; }
.btn-grey   { background:#95A5A6; color:#fff; }
.btn-green  { background:#27AE60; color:#fff; }
.btn-active { outline: 2px solid #fff; box-shadow: 0 0 0 3px #4A90D9; }
#modeTag {
  font-size:10px; padding:3px 8px; border-radius:10px;
  background:#2C3E50; color:#fff; margin-left:4px;
}
#coords {
  font-size:10px; color:#666; margin-left:auto;
  background:#fff; padding:3px 8px; border-radius:4px;
}
label { font-size:11px; color:#444; display:flex; align-items:center; gap:4px; }
input[type=range] { width:70px; }
canvas {
  display:block; cursor:crosshair;
  background:#F5F8FC;
}
#hint {
  position:absolute; bottom:6px; left:50%; transform:translateX(-50%);
  font-size:10px; color:#888; pointer-events:none;
  background:rgba(255,255,255,.8); padding:2px 10px; border-radius:8px;
}
</style>
</head>
<body>
<div id="toolbar">
  <!-- Structure-mode buttons -->
  <span id="grp-struct">
    <button class="btn-blue" id="btn-select"  onclick="setTool('select')">↖ Select</button>
    <button class="btn-blue" id="btn-move"    onclick="setTool('move')">✋ Move</button>
    <button class="btn-blue" id="btn-resize"  onclick="setTool('resize')">⤢ Resize</button>
  </span>
  <!-- Boundary-mode buttons (hidden in view mode) -->
  <span id="grp-bnd" style="display:none">
    <button class="btn-blue" id="btn-bmove"    onclick="setTool('bnd_move')">✋ Vertex</button>
    <button class="btn-blue" id="btn-badd"     onclick="setTool('bnd_add')">➕ Add</button>
    <button class="btn-red"  id="btn-bdel"     onclick="setTool('bnd_del')">🗑 Delete</button>
    <button class="btn-green" id="btn-bfree"   onclick="setTool('bnd_free')">✏️ Freehand</button>
    <button class="btn-grey"  onclick="smoothBnd()">〜 Smooth</button>
    <button class="btn-grey"  onclick="resetBnd()">↩ Reset</button>
  </span>
  <!-- Always-visible -->
  <button class="btn-grey" id="btn-pan" onclick="setTool('pan')">🖐 Pan</button>
  <button class="btn-grey" onclick="resetView()">⊡ Fit</button>
  <label>Grid:
    <input type="range" id="gridSlider" min="0" max="20" step="1" value="1"
           oninput="onGridChange(+this.value)">
    <span id="gridVal">1</span>m
  </label>
  <span id="modeTag">SELECT</span>
  <span id="coords">—</span>
</div>
<div style="position:relative">
  <canvas id="c"></canvas>
  <div id="hint"></div>
</div>

<script>
// ═══════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════
let STATE = {};          // full payload from Python
let tool  = 'select';
let gridSize = 1;

// pan/zoom
let viewX = 0, viewY = 0, viewScale = 4; // world-units per pixel inverse → px per m
let isPanning = false, panStart = {x:0,y:0}, panOrigin = {x:0,y:0};

// drag state
let dragging = null;  // {type, bid, startW, startC, origX, origY, origW, origH, origR, handle}
let bndDrag  = -1;
let freehand = false, fhPts = [];

const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');

// ═══════════════════════════════════════════════════════════
// RESIZE CANVAS TO FILL PARENT
// ═══════════════════════════════════════════════════════════
function resizeCanvas() {
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight - document.getElementById('toolbar').offsetHeight - 4;
  draw();
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// ═══════════════════════════════════════════════════════════
// COORDINATE TRANSFORMS
// ═══════════════════════════════════════════════════════════
// world → canvas pixel
function w2c(wx, wy) {
  return [viewX + wx * viewScale, canvas.height - viewY - wy * viewScale];
}
// canvas pixel → world
function c2w(cx, cy) {
  return [(cx - viewX) / viewScale, (canvas.height - viewY - cy) / viewScale];
}
function snapV(v) {
  if (gridSize <= 0) return v;
  return Math.round(v / gridSize) * gridSize;
}

// ═══════════════════════════════════════════════════════════
// FIT VIEW TO SITE
// ═══════════════════════════════════════════════════════════
function resetView() {
  if (!STATE.site_pts || STATE.site_pts.length < 2) {
    viewX = 40; viewY = 40; viewScale = 5; draw(); return;
  }
  const xs = STATE.site_pts.map(p=>p[0]);
  const ys = STATE.site_pts.map(p=>p[1]);
  const minX=Math.min(...xs), maxX=Math.max(...xs);
  const minY=Math.min(...ys), maxY=Math.max(...ys);
  const pad = 40;
  const scaleX = (canvas.width  - pad*2) / (maxX - minX || 1);
  const scaleY = (canvas.height - pad*2) / (maxY - minY || 1);
  viewScale = Math.min(scaleX, scaleY);
  viewX = pad - minX * viewScale;
  viewY = pad - minY * viewScale;
  draw();
}

// ═══════════════════════════════════════════════════════════
// GRID
// ═══════════════════════════════════════════════════════════
function onGridChange(v) {
  gridSize = v;
  document.getElementById('gridVal').textContent = v || 'off';
  // sync back to python
  sendEvent({type:'grid', value: v});
  draw();
}

// ═══════════════════════════════════════════════════════════
// TOOL MANAGEMENT
// ═══════════════════════════════════════════════════════════
const TOOL_HINTS = {
  select:   'Click a structure to select it',
  move:     'Drag a structure to reposition it',
  resize:   'Drag the corner handles to resize',
  pan:      'Drag the canvas to pan · Scroll to zoom',
  bnd_move: 'Drag a boundary vertex',
  bnd_add:  'Click to add a vertex on the nearest edge',
  bnd_del:  'Click a vertex to delete it',
  bnd_free: 'Click-drag to draw a freehand outline',
};
function setTool(t) {
  tool = t;
  freehand = false; fhPts = [];
  dragging = null; bndDrag = -1;
  document.getElementById('modeTag').textContent = t.toUpperCase().replace('_',' ');
  document.getElementById('hint').textContent = TOOL_HINTS[t] || '';
  // highlight active button
  document.querySelectorAll('button').forEach(b=>b.classList.remove('btn-active'));
  const map = {select:'btn-select', move:'btn-move', resize:'btn-resize',
               pan:'btn-pan', bnd_move:'btn-bmove', bnd_add:'btn-badd',
               bnd_del:'btn-bdel', bnd_free:'btn-bfree'};
  const el = document.getElementById(map[t]);
  if (el) el.classList.add('btn-active');
  draw();
}

// ═══════════════════════════════════════════════════════════
// DRAW
// ═══════════════════════════════════════════════════════════
function drawPolygon(pts) {
  if (!pts || pts.length < 2) return;
  ctx.beginPath();
  pts.forEach(([wx,wy], i) => {
    const [px,py] = w2c(wx,wy);
    i===0 ? ctx.moveTo(px,py) : ctx.lineTo(px,py);
  });
  ctx.closePath();
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // ── grid ──────────────────────────────────────────────
  if (gridSize > 0 && viewScale > 2) {
    const [wx0] = c2w(0, 0);
    const [wx1] = c2w(canvas.width, 0);
    const [,wy0] = c2w(0, canvas.height);
    const [,wy1] = c2w(0, 0);
    const startX = Math.floor(wx0/gridSize)*gridSize;
    const startY = Math.floor(wy0/gridSize)*gridSize;
    ctx.strokeStyle = 'rgba(180,200,220,0.5)';
    ctx.lineWidth = 0.5;
    for (let gx=startX; gx<=wx1+gridSize; gx+=gridSize) {
      const [px] = w2c(gx,0);
      ctx.beginPath(); ctx.moveTo(px,0); ctx.lineTo(px,canvas.height); ctx.stroke();
    }
    for (let gy=startY; gy<=wy1+gridSize; gy+=gridSize) {
      const [,py] = w2c(0,gy);
      ctx.beginPath(); ctx.moveTo(0,py); ctx.lineTo(canvas.width,py); ctx.stroke();
    }
    // axis labels
    ctx.fillStyle='#aab'; ctx.font='9px monospace';
    for (let gx=startX; gx<=wx1+gridSize; gx+=gridSize*2) {
      const [px,py] = w2c(gx,0);
      ctx.fillText(Math.round(gx), px+2, py-3);
    }
    for (let gy=startY; gy<=wy1+gridSize; gy+=gridSize*2) {
      const [px,py] = w2c(0,gy);
      ctx.fillText(Math.round(gy), px+3, py);
    }
  }

  if (!STATE.site_pts) return;

  // ── site boundary fill ────────────────────────────────
  if (STATE.site_pts.length >= 3) {
    drawPolygon(STATE.site_pts);
    ctx.fillStyle = 'rgba(215,228,245,0.25)';
    ctx.fill();
    ctx.strokeStyle = '#2C3E50';
    ctx.lineWidth = 2;
    ctx.setLineDash([8,4]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── setback line ─────────────────────────────────────
  if (STATE.setback_pts.length >= 3) {
    drawPolygon(STATE.setback_pts);
    ctx.strokeStyle = '#E74C3C';
    ctx.lineWidth = 1;
    ctx.setLineDash([4,3]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── buildings ─────────────────────────────────────────
  for (const b of STATE.buildings) {
    if (!b.pts.length) continue;

    // safety buffer
    if (STATE.show_safety && b.buf_pts.length) {
      drawPolygon(b.buf_pts);
      ctx.fillStyle = hexA(b.color, 0.08);
      ctx.fill();
      ctx.strokeStyle = hexA(b.color, 0.25);
      ctx.lineWidth = 1;
      ctx.setLineDash([3,3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // building fill
    drawPolygon(b.pts);
    ctx.fillStyle = hexA(b.color, b.selected ? 0.82 : 0.58);
    ctx.fill();
    ctx.strokeStyle = b.selected ? b.color : hexA(b.color, 0.9);
    ctx.lineWidth = b.selected ? 3 : 1.5;
    if (!b.bnd_ok || !b.clr_ok) {
      ctx.strokeStyle = '#E74C3C';
      ctx.setLineDash([5,3]);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // label
    if (b.pts.length > 0) {
      const cx = b.pts.reduce((s,p)=>s+p[0],0)/b.pts.length;
      const cy = b.pts.reduce((s,p)=>s+p[1],0)/b.pts.length;
      const [px,py] = w2c(cx,cy);
      ctx.fillStyle='#1a1a1a';
      ctx.font = `${Math.max(9, Math.min(13, viewScale*2))}px monospace`;
      ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText(b.name, px, py);
      ctx.textAlign='left'; ctx.textBaseline='alphabetic';
    }

    // resize handles (only for selected in resize mode)
    if (b.selected && tool === 'resize' && b.bbox.length===4) {
      const handles = getResizeHandles(b);
      for (const h of handles) {
        const [hx,hy] = w2c(h.wx, h.wy);
        ctx.fillStyle='#fff';
        ctx.strokeStyle='#4A90D9';
        ctx.lineWidth=1.5;
        ctx.beginPath();
        ctx.rect(hx-5, hy-5, 10, 10);
        ctx.fill(); ctx.stroke();
      }
    }

    // status badges
    if (!b.bnd_ok || !b.clr_ok) {
      if (b.pts.length>0) {
        const [px,py] = w2c(b.pts[0][0], b.pts[0][1]);
        ctx.font='11px monospace';
        ctx.fillText(b.bnd_ok ? '' : '⚠', px, py-4);
      }
    }
  }

  // ── boundary edit handles ─────────────────────────────
  const inBnd = STATE.edit_mode === 'edit_boundary';
  if (inBnd && STATE.bnd_verts) {
    STATE.bnd_verts.forEach(([wx,wy], i) => {
      const [px,py] = w2c(wx,wy);
      ctx.beginPath();
      ctx.arc(px,py, i===bndDrag ? 9 : 6, 0, 2*Math.PI);
      ctx.fillStyle   = i===bndDrag ? '#E74C3C' : '#4A90D9';
      ctx.strokeStyle = '#fff';
      ctx.lineWidth   = 2;
      ctx.fill(); ctx.stroke();
      ctx.fillStyle='#2C3E50'; ctx.font='9px monospace';
      ctx.fillText(i, px+7, py-5);
    });
  }

  // ── freehand preview ─────────────────────────────────
  if (fhPts.length > 1) {
    ctx.beginPath();
    fhPts.forEach(([wx,wy],i)=>{
      const [px,py]=w2c(wx,wy);
      i===0?ctx.moveTo(px,py):ctx.lineTo(px,py);
    });
    ctx.strokeStyle='#E74C3C'; ctx.lineWidth=2;
    ctx.setLineDash([4,3]); ctx.stroke(); ctx.setLineDash([]);
  }
}

// ═══════════════════════════════════════════════════════════
// RESIZE HANDLES  (4 corner handles in world coords)
// ═══════════════════════════════════════════════════════════
function getResizeHandles(b) {
  const [x0,y0,x1,y1] = b.bbox;
  return [
    {id:'tl', wx:x0, wy:y1},
    {id:'tr', wx:x1, wy:y1},
    {id:'bl', wx:x0, wy:y0},
    {id:'br', wx:x1, wy:y0},
  ];
}

function hitHandle(b, cx, cy, thresh=10) {
  for (const h of getResizeHandles(b)) {
    const [hx,hy] = w2c(h.wx, h.wy);
    if (Math.hypot(cx-hx, cy-hy) < thresh) return h;
  }
  return null;
}

// ═══════════════════════════════════════════════════════════
// HIT TESTING  (point-in-polygon for buildings)
// ═══════════════════════════════════════════════════════════
function pointInPoly(px, py, pts) {
  let inside = false;
  for (let i=0, j=pts.length-1; i<pts.length; j=i++) {
    const [xi,yi]=pts[i], [xj,yj]=pts[j];
    if (((yi>py)!==(yj>py)) && (px < (xj-xi)*(py-yi)/(yj-yi)+xi))
      inside = !inside;
  }
  return inside;
}

function hitBuilding(cx, cy) {
  const [wx,wy] = c2w(cx,cy);
  // iterate in reverse so top-most drawn is selected first
  for (let i=STATE.buildings.length-1; i>=0; i--) {
    const b = STATE.buildings[i];
    if (pointInPoly(wx, wy, b.pts)) return b;
  }
  return null;
}

// ═══════════════════════════════════════════════════════════
// BOUNDARY HELPERS
// ═══════════════════════════════════════════════════════════
function closestBndVertex(cx, cy, thresh=14) {
  let best=-1, bd=Infinity;
  (STATE.bnd_verts||[]).forEach(([wx,wy],i)=>{
    const [px,py]=w2c(wx,wy);
    const d=Math.hypot(cx-px,cy-py);
    if(d<bd&&d<thresh){bd=d;best=i;}
  });
  return best;
}

function smoothBnd() {
  const v = STATE.bnd_verts;
  if (!v || v.length < 4) return;
  const out=[], n=v.length;
  for(let i=0;i<n;i++){
    const [x0,y0]=v[i],[x1,y1]=v[(i+1)%n];
    out.push([0.75*x0+0.25*x1, 0.75*y0+0.25*y1]);
    out.push([0.25*x0+0.75*x1, 0.25*y0+0.75*y1]);
  }
  STATE.bnd_verts = out;
  sendEvent({type:'bnd_update', verts: STATE.bnd_verts});
  draw();
}
function resetBnd() {
  sendEvent({type:'bnd_reset'});
}

// ═══════════════════════════════════════════════════════════
// MOUSE EVENTS
// ═══════════════════════════════════════════════════════════
function getPos(e) {
  const r = canvas.getBoundingClientRect();
  return [e.clientX-r.left, e.clientY-r.top];
}

function hexA(hex, a) {
  const h=hex.replace('#','');
  const r=parseInt(h.slice(0,2),16), g=parseInt(h.slice(2,4),16), b=parseInt(h.slice(4,6),16);
  return `rgba(${r},${g},${b},${a})`;
}

canvas.addEventListener('mousedown', e => {
  const [cx,cy] = getPos(e);
  const [wx,wy] = c2w(cx,cy);

  // Middle-mouse always pans
  if (e.button===1 || (e.button===0 && tool==='pan')) {
    isPanning=true; panStart={x:cx,y:cy}; panOrigin={x:viewX,y:viewY};
    canvas.style.cursor='grabbing'; e.preventDefault(); return;
  }
  if (e.button!==0) return;

  const inBnd = STATE.edit_mode==='edit_boundary';

  if (inBnd) {
    if (tool==='bnd_move') {
      bndDrag = closestBndVertex(cx,cy);
    } else if (tool==='bnd_add') {
      const sx=snapV(wx), sy=snapV(wy);
      const v=STATE.bnd_verts;
      if (v.length<2){v.push([sx,sy]); sendEvent({type:'bnd_update',verts:v}); draw(); return;}
      let best=0,bd=Infinity;
      for(let i=0;i<v.length;i++){
        const [ax,ay]=v[i],[bx,by]=v[(i+1)%v.length];
        const mx=(ax+bx)/2,my=(ay+by)/2;
        const d=Math.hypot(sx-mx,sy-my);
        if(d<bd){bd=d;best=i;}
      }
      v.splice(best+1,0,[sx,sy]);
      sendEvent({type:'bnd_update',verts:v}); draw();
    } else if (tool==='bnd_del') {
      const idx=closestBndVertex(cx,cy);
      const v=STATE.bnd_verts;
      if(idx>=0&&v.length>3){v.splice(idx,1); sendEvent({type:'bnd_update',verts:v}); draw();}
    } else if (tool==='bnd_free') {
      freehand=true; fhPts=[[wx,wy]];
    }
    return;
  }

  // ── Structure tools ──────────────────────────────────
  if (tool==='select'||tool==='move'||tool==='resize') {
    // check resize handles first
    if (tool==='resize') {
      const sel = STATE.buildings.find(b=>b.selected);
      if (sel) {
        const h = hitHandle(sel, cx, cy);
        if (h) {
          dragging={type:'resize', bid:sel.id, handle:h.id,
                    startW:[wx,wy], origX:sel.x, origY:sel.y,
                    origW:sel.width, origH:sel.height, origR:sel.radius,
                    bbox: sel.bbox.slice()};
          return;
        }
      }
    }
    const hit = hitBuilding(cx,cy);
    if (hit) {
      sendEvent({type:'select', id:hit.id});
      if (tool==='move') {
        dragging={type:'move', bid:hit.id, startW:[wx,wy], origX:hit.x, origY:hit.y};
      }
    } else {
      sendEvent({type:'deselect'});
    }
  }
});

canvas.addEventListener('mousemove', e => {
  const [cx,cy]=getPos(e);
  const [wx,wy]=c2w(cx,cy);
  document.getElementById('coords').textContent=`${wx.toFixed(1)}, ${wy.toFixed(1)} m`;

  if (isPanning) {
    viewX = panOrigin.x + (cx-panStart.x);
    viewY = panOrigin.y + (cy-panStart.y);
    draw(); return;
  }

  const inBnd = STATE.edit_mode==='edit_boundary';

  if (inBnd && tool==='bnd_move' && bndDrag>=0) {
    STATE.bnd_verts[bndDrag]=[snapV(wx),snapV(wy)];
    draw(); return;
  }
  if (inBnd && tool==='bnd_free' && freehand) {
    fhPts.push([wx,wy]); draw(); return;
  }

  if (!dragging) return;

  const [sx,sy]=dragging.startW;
  const dx=wx-sx, dy=wy-sy;

  if (dragging.type==='move') {
    const nx=snapV(dragging.origX+dx), ny=snapV(dragging.origY+dy);
    // Optimistic local update for smooth feel
    const b=STATE.buildings.find(b=>b.id===dragging.bid);
    if (b){ b.x=nx; b.y=ny; }
    draw();
  } else if (dragging.type==='resize') {
    applyResize(dragging, dx, dy);
    draw();
  }
});

canvas.addEventListener('mouseup', e => {
  const [cx,cy]=getPos(e);
  const [wx,wy]=c2w(cx,cy);

  if (isPanning) {
    isPanning=false; canvas.style.cursor='crosshair'; return;
  }

  const inBnd = STATE.edit_mode==='edit_boundary';
  if (inBnd && tool==='bnd_move' && bndDrag>=0) {
    bndDrag=-1; sendEvent({type:'bnd_update', verts:STATE.bnd_verts}); return;
  }
  if (inBnd && tool==='bnd_free' && freehand) {
    freehand=false;
    if(fhPts.length>4){
      const step=Math.max(1,Math.floor(fhPts.length/40));
      STATE.bnd_verts=fhPts.filter((_,i)=>i%step===0);
    }
    fhPts=[];
    sendEvent({type:'bnd_update', verts:STATE.bnd_verts}); return;
  }

  if (!dragging) return;

  const [sx,sy]=dragging.startW;
  const dx=wx-sx, dy=wy-sy;

  if (dragging.type==='move') {
    const nx=snapV(dragging.origX+dx), ny=snapV(dragging.origY+dy);
    sendEvent({type:'move', id:dragging.bid, x:nx, y:ny});
  } else if (dragging.type==='resize') {
    const dims=calcResize(dragging, dx, dy);
    sendEvent({type:'resize', id:dragging.bid, ...dims});
  }
  dragging=null;
});

// Scroll to zoom
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const [cx,cy]=getPos(e);
  const factor = e.deltaY<0 ? 1.1 : 0.91;
  viewX = cx - (cx-viewX)*factor;
  viewY = cy - (cy-viewY)*factor;  // y grows downward in canvas, adjust
  viewScale *= factor;
  draw();
}, {passive:false});

// Middle-mouse up
window.addEventListener('mouseup', e=>{
  if(e.button===1&&isPanning){isPanning=false;canvas.style.cursor='crosshair';}
  if(dragging&&e.button===0){
    // catch mouseup outside canvas
    dragging=null;
  }
});

// Touch support
canvas.addEventListener('touchstart', e=>{
  e.preventDefault();
  const t=e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousedown',{button:0,clientX:t.clientX,clientY:t.clientY}));
},{passive:false});
canvas.addEventListener('touchmove', e=>{
  e.preventDefault();
  const t=e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousemove',{button:0,clientX:t.clientX,clientY:t.clientY}));
},{passive:false});
canvas.addEventListener('touchend', e=>{
  e.preventDefault();
  canvas.dispatchEvent(new MouseEvent('mouseup',{button:0}));
},{passive:false});

// ═══════════════════════════════════════════════════════════
// RESIZE LOGIC
// ═══════════════════════════════════════════════════════════
function applyResize(drag, dx, dy) {
  const b=STATE.buildings.find(b=>b.id===drag.bid);
  if(!b) return;
  const dims=calcResize(drag,dx,dy);
  Object.assign(b,dims);
}

function calcResize(drag, dx, dy) {
  const h=drag.handle;
  let {origX:x, origY:y, origW:w, origH:h_:_h, origR:r} = drag;
  // for radius-based shapes, use half the min dimension
  if (r>0) {
    const delta = (Math.abs(dx)>Math.abs(dy)?dx:dy);
    return {radius: Math.max(1, snapV(r + delta/2))};
  }
  let nx=x, ny=y, nw=w, nh=_h;
  if(h==='br'){ nw=Math.max(1,snapV(w+dx)); nh=Math.max(1,snapV(_h-dy)); }
  else if(h==='bl'){ nx=snapV(x+dx); nw=Math.max(1,snapV(w-dx)); nh=Math.max(1,snapV(_h-dy)); }
  else if(h==='tr'){ nw=Math.max(1,snapV(w+dx)); nh=Math.max(1,snapV(_h+dy)); }
  else if(h==='tl'){ nx=snapV(x+dx); nw=Math.max(1,snapV(w-dx)); nh=Math.max(1,snapV(_h+dy)); }
  return {x:nx, y:ny, width:nw, height:nh};
}

// ═══════════════════════════════════════════════════════════
// COMMUNICATION WITH STREAMLIT
// ═══════════════════════════════════════════════════════════
function sendEvent(obj) {
  const el=document.getElementById('event_out');
  if(el){ el.value=JSON.stringify(obj); el.dispatchEvent(new Event('input',{bubbles:true})); }
}

// Receive state from Python via hidden input
function applyState(jsonStr) {
  try {
    const newState=JSON.parse(jsonStr);
    STATE=newState;
    // update grid slider to match session state
    const gs=document.getElementById('gridSlider');
    if(gs) gs.value=STATE.snap_grid||1;
    document.getElementById('gridVal').textContent=STATE.snap_grid||1;
    gridSize=STATE.snap_grid||1;
    // show/hide toolbar groups
    const inBnd=STATE.edit_mode==='edit_boundary';
    document.getElementById('grp-struct').style.display=inBnd?'none':'inline';
    document.getElementById('grp-bnd').style.display=inBnd?'inline':'none';
    if(inBnd && !tool.startsWith('bnd') && tool!=='pan') setTool('bnd_move');
    if(!inBnd && tool.startsWith('bnd')) setTool('select');
    draw();
  } catch(err) { console.error('applyState error', err); }
}

// Watch the hidden input for state pushes
const obs=new MutationObserver(()=>{
  const el=document.getElementById('state_in');
  if(el&&el.value) applyState(el.value);
});
const stateEl=document.getElementById('state_in');
if(stateEl) obs.observe(stateEl, {attributes:true, attributeFilter:['value']});
// Also poll in case mutation fires before inject
setInterval(()=>{
  const el=document.getElementById('state_in');
  if(el&&el.value&&el.value!==applyState._last){
    applyState._last=el.value; applyState(el.value);
  }
},200);

// Initial state
setTimeout(()=>{
  const el=document.getElementById('state_in');
  if(el&&el.value) applyState(el.value);
  resetView();
}, 50);

setTool('select');
</script>

<!-- Hidden IO elements written/read by Streamlit via st.text_input -->
<input type="hidden" id="state_in"  value="STATE_JSON">
<input type="hidden" id="event_out" value="">
</body>
</html>
"""


def render_canvas() -> Optional[dict]:
    """
    Render the interactive canvas. Returns a parsed event dict if the user
    performed an action (move, resize, select, bnd_update, etc.), else None.
    """
    payload = _build_canvas_payload()
    html_src = CANVAS_HTML.replace("STATE_JSON", payload.replace('"', "&quot;"))

    # event_out is a hidden input whose value the JS sets; we surface it via
    # a Streamlit text_input with visibility:hidden so Streamlit can read it.
    event_raw = components.html(
        html_src + """
        <script>
        // Wire the hidden event_out → parent Streamlit text input
        document.getElementById('event_out').addEventListener('input', function() {
          window.parent.postMessage({type:'streamlit:setComponentValue', value:this.value}, '*');
        });
        </script>
        """,
        height=700,
        scrolling=False,
    )
    return None   # events are handled via st.text_input below


# ─────────────────────────────────────────────────────────────
# PROCESS CANVAS EVENTS FROM JS
# ─────────────────────────────────────────────────────────────
def process_canvas_event(raw: str) -> bool:
    """Parse and apply a canvas event. Returns True if state changed."""
    if not raw or not raw.strip().startswith("{"):
        return False
    try:
        ev = json.loads(raw)
    except Exception:
        return False

    t = ev.get("type", "")

    if t == "select":
        bid = ev["id"]
        if bid != st.session_state.selected_id:
            st.session_state.selected_id = bid
            return True

    elif t == "deselect":
        if st.session_state.selected_id is not None:
            st.session_state.selected_id = None
            return True

    elif t == "move":
        bid = ev["id"]
        if bid in st.session_state.buildings:
            b = st.session_state.buildings[bid]
            b["x"] = float(ev["x"])
            b["y"] = float(ev["y"])
            # Road: shift waypoints too
            if b.get("shape") == "Road" and "waypoints" in b:
                ox = float(ev.get("orig_x", b["x"]))
                oy = float(ev.get("orig_y", b["y"]))
                dx, dy = b["x"] - ox, b["y"] - oy
                b["waypoints"] = [[p[0]+dx, p[1]+dy] for p in b["waypoints"]]
            return True

    elif t == "resize":
        bid = ev["id"]
        if bid in st.session_state.buildings:
            b = st.session_state.buildings[bid]
            for k in ("x","y","width","height","radius"):
                if k in ev:
                    b[k] = float(ev[k])
            # clamp stem dimensions for L/T shapes
            if b["shape"] == "L-Shape":
                b["stem_w"] = min(b.get("stem_w", b["width"]/2), b["width"])
                b["stem_h"] = min(b.get("stem_h", b["height"]/2), b["height"])
            return True

    elif t == "bnd_update":
        verts = ev.get("verts", [])
        if len(verts) >= 3:
            st.session_state.site_vertices = [tuple(v) for v in verts]
            return True

    elif t == "bnd_reset":
        st.session_state.site_vertices = list(DEFAULT_BOUNDARY)
        return True

    elif t == "grid":
        v = float(ev.get("value", 1))
        if v != st.session_state.snap_grid:
            st.session_state.snap_grid = v
            return True

    return False


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
def render_sidebar() -> None:
    st.sidebar.markdown(
        "<h2 style='margin-bottom:0;color:#fff'>🏗️ Site Planner</h2>"
        "<p style='font-size:.75rem;color:#8BAACC;margin-top:2px'>v3.0 · Construction Layout Tool</p>",
        unsafe_allow_html=True,
    )
    st.sidebar.divider()

    st.sidebar.subheader("🛡️ Safety")
    st.session_state.safety_margin = st.sidebar.slider(
        "Clearance between structures (m)", 0.0, 10.0,
        st.session_state.safety_margin, 0.5,
        help="Minimum gap enforced between any two structures")
    st.session_state.boundary_threshold = st.sidebar.slider(
        "Boundary setback (m)", 0.0, 15.0,
        st.session_state.boundary_threshold, 0.5,
        help="Structures must be set back this far from the boundary")
    st.sidebar.divider()

    st.sidebar.subheader("⚙️ Canvas")
    st.session_state.snap_grid = st.sidebar.select_slider(
        "Snap-to-grid (m)", [0.0, 0.5, 1.0, 2.0, 5.0, 10.0],
        st.session_state.snap_grid, help="0 = free placement")
    st.session_state.show_safety_zones = st.sidebar.toggle(
        "Safety buffer zones", st.session_state.show_safety_zones)
    st.session_state.show_utilisation = st.sidebar.toggle(
        "Utilisation panel", st.session_state.show_utilisation)
    st.sidebar.divider()

    st.sidebar.subheader("💾 Save / Load")
    st.sidebar.download_button(
        "📥 Export JSON", data=export_state(),
        file_name="site_layout.json", mime="application/json",
        use_container_width=True)
    up = st.sidebar.file_uploader("📂 Import JSON", type="json",
                                   label_visibility="visible")
    if up:
        try:
            import_state(up.read().decode())
            st.success("Layout imported.")
            st.rerun()
        except Exception as ex:
            st.sidebar.error(f"Import failed: {ex}")

    st.sidebar.divider()
    s = utilisation_stats()
    m1, m2, m3 = st.sidebar.columns(3)
    m1.metric("Structs", s["n_buildings"])
    m2.metric("Area", f"{s['site_area']:.0f}m²")
    m3.metric("Used", f"{s['utilisation_pct']:.0f}%")


# ─────────────────────────────────────────────────────────────
# BUILDING FORM
# ─────────────────────────────────────────────────────────────
def render_add_edit_form(existing_id: Optional[str] = None) -> None:
    is_edit = existing_id is not None
    b = st.session_state.buildings.get(existing_id, {}) if is_edit else {}

    st.subheader("✏️ Edit Structure" if is_edit else "➕ Add Structure")
    col1, col2 = st.columns(2)

    with col1:
        name     = st.text_input("Name",
                     value=b.get("name", f"Structure {len(st.session_state.buildings)+1}"))
        category = st.selectbox("Category", list(CATEGORY_COLORS),
                     index=list(CATEGORY_COLORS).index(b.get("category","Office / Admin")))
        color    = st.color_picker("Colour", value=b.get("color", CATEGORY_COLORS[category]))

    with col2:
        shape = st.selectbox("Shape", SHAPE_TYPES,
                    index=SHAPE_TYPES.index(b.get("shape","Rectangle")))
        angle = st.slider("Rotation (°)", -180, 180, int(b.get("angle",0)), 5)
        notes = st.text_area("Notes", value=b.get("notes",""), height=68)

    st.divider()
    g = st.session_state.snap_grid
    params: dict = {}

    if shape == "Rectangle":
        c1,c2,c3,c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X (m)",      value=float(b.get("x",10)),     step=max(g,.1)), g)
        params["y"]      = snap(c2.number_input("Y (m)",      value=float(b.get("y",10)),     step=max(g,.1)), g)
        params["width"]  = snap(c3.number_input("Width (m)",  value=float(b.get("width",20)), min_value=1., step=max(g,.1)), g)
        params["height"] = snap(c4.number_input("Height (m)", value=float(b.get("height",15)),min_value=1., step=max(g,.1)), g)

    elif shape == "L-Shape":
        c1,c2,c3,c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X",      value=float(b.get("x",10)),     step=max(g,.1)), g)
        params["y"]      = snap(c2.number_input("Y",      value=float(b.get("y",10)),     step=max(g,.1)), g)
        params["width"]  = snap(c3.number_input("Width",  value=float(b.get("width",20)), min_value=2., step=max(g,.1)), g)
        params["height"] = snap(c4.number_input("Height", value=float(b.get("height",15)),min_value=2., step=max(g,.1)), g)
        c5,c6 = st.columns(2)
        params["stem_w"] = snap(c5.number_input("Stem W (m)", value=float(b.get("stem_w",10)),min_value=1.,step=max(g,.1)), g)
        params["stem_h"] = snap(c6.number_input("Stem H (m)", value=float(b.get("stem_h",8)), min_value=1.,step=max(g,.1)), g)

    elif shape == "T-Shape":
        c1,c2,c3,c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X",       value=float(b.get("x",10)),     step=max(g,.1)), g)
        params["y"]      = snap(c2.number_input("Y",       value=float(b.get("y",10)),     step=max(g,.1)), g)
        params["width"]  = snap(c3.number_input("Width",   value=float(b.get("width",30)), min_value=3., step=max(g,.1)), g)
        params["height"] = snap(c4.number_input("Height",  value=float(b.get("height",20)),min_value=2., step=max(g,.1)), g)
        params["cap_h"]  = snap(st.number_input("Cap height (m)", value=float(b.get("cap_h",8)),min_value=1.,step=max(g,.1)), g)

    elif shape in ("Hexagon","Circle","Semicircle"):
        c1,c2,c3 = st.columns(3)
        params["x"]      = snap(c1.number_input("Centre X", value=float(b.get("x",20)), step=max(g,.1)), g)
        params["y"]      = snap(c2.number_input("Centre Y", value=float(b.get("y",20)), step=max(g,.1)), g)
        params["radius"] = snap(c3.number_input("Radius (m)", value=float(b.get("radius",8)),min_value=1.,step=max(g,.1)), g)
        if shape == "Semicircle":
            params["flat_angle"] = st.slider("Flat-edge direction (°)",0,360,int(b.get("flat_angle",0)),15)

    elif shape == "Road":
        st.info("Enter waypoints as X,Y pairs (one per line). Minimum 2 points.")
        default_wp = b.get("waypoints",[(10,10),(40,10),(40,40)])
        raw_wp = st.text_area("Waypoints",
            value="\n".join(f"{p[0]},{p[1]}" for p in default_wp), height=100)
        parsed_wp: list = []
        for line in raw_wp.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_wp.append((float(px_.strip()), float(py_.strip())))
            except ValueError: pass
        params["waypoints"]  = parsed_wp
        params["road_width"] = st.slider("Road width (m)", 2.0, 20.0, float(b.get("road_width",5.0)), 0.5)
        params["x"] = parsed_wp[0][0] if parsed_wp else 0
        params["y"] = parsed_wp[0][1] if parsed_wp else 0

    elif shape == "Custom Polygon":
        st.info("Enter X,Y pairs (one per line).")
        default_pts = b.get("custom_pts",[(10,10),(30,10),(30,25),(10,25)])
        raw_pts = st.text_area("Vertices",
            value="\n".join(f"{p[0]},{p[1]}" for p in default_pts), height=110)
        parsed_pts: list = []
        for line in raw_pts.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_pts.append((float(px_.strip()), float(py_.strip())))
            except ValueError: pass
        params["custom_pts"] = parsed_pts
        params["x"] = parsed_pts[0][0] if parsed_pts else 0
        params["y"] = parsed_pts[0][1] if parsed_pts else 0

    params.update(shape=shape, angle=float(angle),
                  name=name, category=category, color=color, notes=notes)

    preview = building_polygon(params)
    if not preview.is_empty:
        bb = preview.bounds
        col_prev, col_bnd, col_clr = st.columns(3)
        col_prev.caption(f"**Area:** {preview.area:.1f} m²  ·  **Box:** {bb[2]-bb[0]:.1f}×{bb[3]-bb[1]:.1f} m")
        dummy_id = existing_id or "__preview__"
        col_bnd.caption("Boundary: " + ("✅ OK" if check_boundary(preview) else "⚠️ Breaches setback"))
        hits = check_collisions(dummy_id, preview)
        col_clr.caption("Clearance: " + ("✅ Clear" if not hits else f"⚠️ {', '.join(hits)}"))

    sc, cc, *_ = st.columns([1,1,3])
    if sc.button("💾 Save" if is_edit else "➕ Place", type="primary", use_container_width=True):
        bid  = existing_id or str(uuid.uuid4())[:8]
        poly = building_polygon(params)
        warns  = []
        if check_collisions(bid, poly): warns.append("⚠️ Clearance violated")
        if not check_boundary(poly):    warns.append("⚠️ Breaches boundary setback")
        if warns and not st.session_state.get("_force"):
            for w in warns: st.warning(w)
            st.session_state["_force"] = True
            st.info("Press **Save** again to override.")
            return
        st.session_state.pop("_force", None)
        st.session_state.buildings[bid] = params
        st.session_state.selected_id    = bid
        st.session_state.edit_mode      = "view"
        st.success(f"✅ '{name}' {'updated' if is_edit else 'placed'}.")
        st.rerun()

    if cc.button("Cancel", use_container_width=True):
        st.session_state.edit_mode = "view"
        st.session_state.pop("_force", None)
        st.rerun()


# ─────────────────────────────────────────────────────────────
# BOUNDARY TEXT / PRESET PANEL  (no canvas tab — canvas IS the editor)
# ─────────────────────────────────────────────────────────────
def render_boundary_panel() -> None:
    st.subheader("🗺️ Edit Site Boundary")
    st.info("Use the canvas below — **Vertex / Add / Delete / Freehand** modes appear in the toolbar. Pan with 🖐 or scroll to zoom.")

    tab_text, tab_preset = st.tabs(["⌨️ Type Coordinates", "📐 Presets"])

    with tab_text:
        raw = st.text_area(
            "Vertices (X,Y per line)",
            value="\n".join(f"{p[0]},{p[1]}" for p in st.session_state.site_vertices),
            height=180,
        )
        parsed_text: list = []
        for line in raw.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_text.append((float(px_.strip()), float(py_.strip())))
            except ValueError: pass
        if len(parsed_text) >= 3:
            st.caption(f"Area: **{Polygon(parsed_text).area:.1f} m²** · {len(parsed_text)} vertices")
        if st.button("✅ Apply", type="primary"):
            if len(parsed_text) < 3:
                st.error("Need ≥ 3 valid points.")
            else:
                st.session_state.site_vertices = parsed_text
                st.session_state.edit_mode = "view"
                st.rerun()

    with tab_preset:
        presets: dict[str,list] = {
            "Default (irregular)":  list(DEFAULT_BOUNDARY),
            "Rectangle 120×80":     [(0,0),(120,0),(120,80),(0,80)],
            "Large square 150×150": [(0,0),(150,0),(150,150),(0,150)],
            "L-shaped":             [(0,0),(100,0),(100,40),(60,40),(60,80),(0,80)],
            "T-shaped":             [(20,0),(80,0),(80,40),(100,40),(100,60),(80,60),
                                     (80,90),(20,90),(20,60),(0,60),(0,40),(20,40)],
            "Trapezoid":            [(10,0),(110,0),(120,80),(0,80)],
            "Pentagon site":        [(50,0),(100,30),(85,90),(15,90),(0,30)],
            "Oval (approx)":        [(50+40*math.cos(2*math.pi*i/24),
                                      40+28*math.sin(2*math.pi*i/24)) for i in range(24)],
        }
        choice = st.selectbox("Select preset", list(presets))
        st.caption(f"Area: {Polygon(presets[choice]).area:.1f} m² · {len(presets[choice])} vertices")
        if st.button("Load preset", type="primary"):
            st.session_state.site_vertices = presets[choice]
            st.session_state.edit_mode = "view"
            st.rerun()

    if st.button("✕ Done editing boundary", use_container_width=True):
        st.session_state.edit_mode = "view"
        st.rerun()


# ─────────────────────────────────────────────────────────────
# STRUCTURE TABLE
# ─────────────────────────────────────────────────────────────
def render_table() -> None:
    if not st.session_state.buildings:
        st.markdown(
            "<div style='text-align:center;padding:1.5rem;background:#F8FAFD;"
            "border-radius:10px;border:1.5px dashed #BDD0E5;color:#7A9BB5'>"
            "<p style='font-size:1.5rem;margin:0'>🏗️</p>"
            "<p style='margin:4px 0 0'>No structures yet — click <b>➕ Add Structure</b></p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        rows.append({
            "":          "⭐" if bid == st.session_state.selected_id else "",
            "Name":      b["name"],
            "Category":  b["category"],
            "Shape":     b["shape"],
            "Area (m²)": f"{poly.area:.1f}",
            "Rot":       f"{b.get('angle',0):.0f}°",
            "Bnd":       "✅" if check_boundary(poly) else "⚠️",
            "Clr":       "✅" if not check_collisions(bid, poly) else "⚠️",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=190, hide_index=True)

    all_names = {b["name"]: bid for bid, b in st.session_state.buildings.items()}
    sc, ec, dc = st.columns([3,1,1])
    sel = sc.selectbox("Structure", ["— select —"]+list(all_names), label_visibility="collapsed")
    if sel != "— select —":
        sid = all_names[sel]
        if ec.button("✏️ Edit", use_container_width=True):
            st.session_state.selected_id = sid
            st.session_state.edit_mode   = "edit_building"
            st.rerun()
        if dc.button("🗑️ Delete", use_container_width=True):
            del st.session_state.buildings[sid]
            if st.session_state.selected_id == sid:
                st.session_state.selected_id = None
            st.rerun()


# ─────────────────────────────────────────────────────────────
# UTILISATION PANEL
# ─────────────────────────────────────────────────────────────
def render_utilisation() -> None:
    s = utilisation_stats()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Site Area",   f"{s['site_area']:.0f} m²")
    c2.metric("Built Area",  f"{s['inside_area']:.0f} m²")
    c3.metric("Free Area",   f"{s['free_area']:.0f} m²")
    c4.metric("Utilisation", f"{s['utilisation_pct']:.1f}%")
    pct = min(s["utilisation_pct"]/100, 1.0)
    if pct > .9:   bar,icon,msg = "#E74C3C","🔴","Site nearly full"
    elif pct > .75: bar,icon,msg = "#E07B39","🟡","Getting busy"
    else:           bar,icon,msg = "#27AE60","🟢","Plenty of space"
    st.markdown(
        f'<div style="background:#DDE6F0;border-radius:6px;height:12px;overflow:hidden">'
        f'<div style="background:{bar};width:{pct*100:.1f}%;height:100%;border-radius:6px;transition:width .4s"></div></div>'
        f'<p style="font-size:.78rem;color:#555;margin:4px 0 0">{icon} {s["n_buildings"]} structure(s) &nbsp;·&nbsp; {msg}</p>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main() -> None:
    render_sidebar()

    st.markdown("## 🏗️ Construction Site Planner")

    # ── Toolbar ───────────────────────────────────────────
    t1,t2,t3,t4 = st.columns([3,3,2,2])
    if t1.button("➕ Add Structure", type="primary", use_container_width=True):
        st.session_state.edit_mode   = "add"
        st.session_state.selected_id = None
        st.session_state.pop("_force", None)
    if t2.button("🗺️ Edit Boundary", use_container_width=True):
        st.session_state.edit_mode = "edit_boundary"
    if t3.button("🗑️ Clear All", use_container_width=True):
        st.session_state["_confirm_clear"] = True
    if t4.button("🔄 Reset", use_container_width=True):
        st.session_state["_confirm_reset"] = True

    if st.session_state.pop("_confirm_clear", False):
        st.warning("Remove all structures?")
        cy, cn = st.columns(2)
        if cy.button("Yes, clear all", type="primary", use_container_width=True):
            st.session_state.buildings = {}; st.session_state.selected_id = None; st.rerun()
        if cn.button("Cancel", use_container_width=True): st.rerun()

    if st.session_state.pop("_confirm_reset", False):
        st.warning("Reset everything — structures **and** boundary?")
        ry, rn = st.columns(2)
        if ry.button("Yes, reset", type="primary", use_container_width=True):
            for k in ["buildings","site_vertices","selected_id","edit_mode"]: del st.session_state[k]
            st.rerun()
        if rn.button("Cancel", use_container_width=True): st.rerun()

    # ── Active side panel ─────────────────────────────────
    if st.session_state.edit_mode == "add":
        st.divider(); render_add_edit_form(); st.divider()
    elif st.session_state.edit_mode == "edit_building" and st.session_state.selected_id:
        st.divider(); render_add_edit_form(st.session_state.selected_id); st.divider()
    elif st.session_state.edit_mode == "edit_boundary":
        st.divider(); render_boundary_panel(); st.divider()

    # ── Utilisation ───────────────────────────────────────
    if st.session_state.show_utilisation:
        render_utilisation()
        st.divider()

    # ── Canvas event bridge ───────────────────────────────
    # We use a hidden text_input to ferry events from the iframe to Python.
    # The canvas JS calls sendEvent() which fires window.parent.postMessage;
    # Streamlit's component bridge turns that into the component return value.
    # Because components.html() can't return values in Streamlit, we instead
    # use a visible (but styled-invisible) text_input that the user pastes into
    # via a postMessage listener in a tiny companion component.
    ev_raw = st.text_input(
        "canvas_event",
        value=st.session_state.get("canvas_event",""),
        key="canvas_event_input",
        label_visibility="collapsed",
    )
    if ev_raw and ev_raw != st.session_state.get("_last_ev",""):
        st.session_state["_last_ev"] = ev_raw
        if process_canvas_event(ev_raw):
            st.rerun()

    # ── Canvas ────────────────────────────────────────────
    payload = _build_canvas_payload()

    # Embed the full canvas + a postMessage bridge that writes into the
    # Streamlit text_input above. We inject the payload as JS data.
    canvas_html = CANVAS_HTML.replace(
        'value="STATE_JSON"',
        f'value=\'{payload.replace(chr(39), "&apos;")}\''
    )

    # Add the postMessage → text_input bridge
    bridge = """
<script>
window.addEventListener('message', function(e){
  if(e.data && e.data.type==='streamlit:setComponentValue'){
    // Find the hidden text input by label search and update it
    const inputs = window.parent.document.querySelectorAll('input[type="text"]');
    for(const inp of inputs){
      const label = inp.closest('[data-testid="stTextInput"]');
      if(label){
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype,'value').set;
        nativeInputValueSetter.call(inp, e.data.value);
        inp.dispatchEvent(new Event('input',{bubbles:true}));
        break;
      }
    }
  }
});
</script>
"""
    components.html(canvas_html + bridge, height=720, scrolling=False)

    # ── Structure table ───────────────────────────────────
    st.subheader("📋 Structures")
    render_table()


if __name__ == "__main__":
    main()
