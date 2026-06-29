"""
Construction Site Planner  ·  v2.0
─────────────────────────────────────────────────────────────────────────────
Features:
  • Shapes  – Rectangle, L-Shape, T-Shape, Hexagon, Circle, Semicircle,
               Road (polyline + width), Custom Polygon
  • Boundary editor – drag vertices directly on the Plotly canvas;
                      free-draw curved outline via freehand SVG tool
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
import plotly.graph_objects as go
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

# ─────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Toolbar buttons ── */
div[data-testid="stHorizontalBlock"] button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: .3px;
}

/* ── Dark sidebar ── */
section[data-testid="stSidebar"] {
    background: #1E2A38 !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small {
    color: #C5D4E3 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 1.3rem !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
    color: #8BAACC !important;
}

/* ── Metric cards in main area ── */
div[data-testid="stMetric"] {
    background: #F0F4FA;
    border-radius: 10px;
    padding: 10px 14px 8px;
    border-left: 4px solid #4A90D9;
}

/* ── Tighter top padding ── */
.block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
CATEGORY_COLORS: dict[str, str] = {
    "Office / Admin":     "#4A90D9",
    "Warehouse":          "#E07B39",
    "Workshop / Lab":     "#6BBF59",
    "Storage Yard":       "#9B59B6",
    "Utility / Plant":    "#F1C40F",
    "Access Road":        "#7F8C8D",
    "Green / Landscape":  "#27AE60",
    "Custom":             "#E74C3C",
}

SHAPE_TYPES = [
    "Rectangle", "L-Shape", "T-Shape",
    "Hexagon", "Circle", "Semicircle",
    "Road", "Custom Polygon",
]

DEFAULT_BOUNDARY: list[tuple[float, float]] = [
    (0, 0), (100, 0), (110, 35), (100, 80), (55, 85), (0, 60),
]

CIRCLE_SEGMENTS = 72   # polygon approximation resolution


# ─────────────────────────────────────────────────────────────
# COLOUR UTILITIES  (Plotly 6+ requires rgba() — no 8-char hex)
# ─────────────────────────────────────────────────────────────
def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert '#RRGGBB' + opacity float → 'rgba(r,g,b,a)' string."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ─────────────────────────────────────────────────────────────
# SESSION-STATE BOOTSTRAP
# ─────────────────────────────────────────────────────────────
def _init() -> None:
    defaults: dict = {
        "buildings":           {},
        "site_vertices":       list(DEFAULT_BOUNDARY),
        "safety_margin":       2.0,
        "boundary_threshold":  1.5,
        "selected_id":         None,
        "edit_mode":           "view",
        "show_safety_zones":   True,
        "show_utilisation":    True,
        "snap_grid":           1.0,
        # boundary-editor state
        "bnd_drag_result":     None,   # JSON string pushed back from JS
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init()


# ─────────────────────────────────────────────────────────────
# GEOMETRY HELPERS
# ─────────────────────────────────────────────────────────────
def _circle_pts(cx: float, cy: float, r: float, n: int = CIRCLE_SEGMENTS
                ) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2 * math.pi * i / n),
         cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def make_rectangle(x, y, w, h, angle=0.0) -> Polygon:
    p = Polygon([(x, y), (x+w, y), (x+w, y+h), (x, y+h)])
    return sh_rotate(p, angle, origin=(x+w/2, y+h/2))


def make_l_shape(x, y, w, h, sw, sh_, angle=0.0) -> Polygon:
    p = Polygon([
        (x, y), (x+w, y), (x+w, y+sh_),
        (x+sw, y+sh_), (x+sw, y+h), (x, y+h),
    ])
    return sh_rotate(p, angle, origin=(x+w/2, y+h/2))


def make_t_shape(x, y, w, h, cap_h, angle=0.0) -> Polygon:
    sw = w / 3
    sx = x + w / 3
    top  = Polygon([(x, y),   (x+w, y),   (x+w, y+cap_h), (x,   y+cap_h)])
    stem = Polygon([(sx, y+cap_h), (sx+sw, y+cap_h),
                    (sx+sw, y+h),  (sx,    y+h)])
    return sh_rotate(top.union(stem), angle, origin=(x+w/2, y+h/2))


def make_hexagon(cx, cy, r, angle=0.0) -> Polygon:
    pts = [
        (cx + r * math.cos(math.radians(60*i)),
         cy + r * math.sin(math.radians(60*i)))
        for i in range(6)
    ]
    return sh_rotate(Polygon(pts), angle, origin=(cx, cy))


def make_circle(cx, cy, r) -> Polygon:
    return Polygon(_circle_pts(cx, cy, r))


def make_semicircle(cx, cy, r, flat_angle=0.0, angle=0.0) -> Polygon:
    """Flat edge at `flat_angle` degrees (0 = flat on bottom, facing up)."""
    n = CIRCLE_SEGMENTS // 2
    pts = [(cx, cy)]
    for i in range(n + 1):
        a = math.radians(flat_angle) + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    p = Polygon(pts)
    return sh_rotate(p, angle, origin=(cx, cy))


def make_road(waypoints: list[tuple[float, float]], width: float) -> Polygon:
    """Buffered polyline — flat end-caps."""
    if len(waypoints) < 2:
        return Polygon()
    ls = LineString(waypoints)
    buf = ls.buffer(width / 2, cap_style=2, join_style=2)
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
                                b.get("stem_w", b["width"]/2),
                                b.get("stem_h", b["height"]/2), angle)
        if s == "T-Shape":
            return make_t_shape(x, y, b["width"], b["height"],
                                b.get("cap_h", b["height"]/3), angle)
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
        and poly.buffer(m/2).intersects(building_polygon(b).buffer(m/2))
    ]


def check_boundary(poly: Polygon) -> bool:
    site = site_polygon()
    if site.is_empty:
        return True
    t = st.session_state.boundary_threshold
    inner = site.buffer(-t)
    return (not inner.is_empty) and inner.contains(poly)


# ─────────────────────────────────────────────────────────────
# PLOTLY FIGURE
# ─────────────────────────────────────────────────────────────
def _add_polygon_trace(fig: go.Figure, poly: Polygon,
                       fill: str, line_color: str, line_width: float,
                       name: str = "", hover: str = "",
                       show_legend: bool = False) -> None:
    geoms = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
    for g in geoms:
        xs, ys = g.exterior.xy
        fig.add_trace(go.Scatter(
            x=list(xs), y=list(ys), fill="toself",
            fillcolor=fill,
            line=dict(color=line_color, width=line_width),
            name=name, text=hover,
            hoverinfo="text" if hover else "skip",
            hoverlabel=dict(bgcolor="white", font_size=12),
            showlegend=show_legend,
        ))


def build_figure(boundary_edit_mode: bool = False) -> go.Figure:
    fig = go.Figure()
    site = site_polygon()

    # ── Site fill ──────────────────────────────────────────
    if not site.is_empty:
        sx, sy = site.exterior.xy
        fig.add_trace(go.Scatter(
            x=list(sx), y=list(sy), fill="toself",
            fillcolor="rgba(215,228,245,0.35)",
            line=dict(color="#2C3E50", width=2.5,
                      dash="dash" if not boundary_edit_mode else "solid"),
            name="Site Boundary", hoverinfo="skip", showlegend=False,
        ))
        # Setback inset — guard against threshold ≥ inradius collapsing to
        # a LineString / Point, neither of which has .exterior
        inner = site.buffer(-st.session_state.boundary_threshold)
        if not inner.is_empty and inner.geom_type in ("Polygon", "MultiPolygon"):
            geoms = [inner] if inner.geom_type == "Polygon" else list(inner.geoms)
            for g in geoms:
                ix, iy = g.exterior.xy
                fig.add_trace(go.Scatter(
                    x=list(ix), y=list(iy),
                    line=dict(color="#E74C3C", width=1, dash="dot"),
                    mode="lines", hoverinfo="skip", showlegend=False,
                ))

    # ── Boundary vertex handles (drag mode) ───────────────
    if boundary_edit_mode:
        vx = [v[0] for v in st.session_state.site_vertices]
        vy = [v[1] for v in st.session_state.site_vertices]
        fig.add_trace(go.Scatter(
            x=vx, y=vy, mode="markers+text",
            marker=dict(size=14, color="#E74C3C",
                        line=dict(color="white", width=2)),
            text=[str(i) for i in range(len(vx))],
            textposition="top center",
            textfont=dict(size=9, color="#2C3E50"),
            name="BoundaryHandles",
            hovertemplate="Vertex %{text}<br>(%{x:.1f}, %{y:.1f})<extra></extra>",
        ))

    # ── Buildings ──────────────────────────────────────────
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        if poly.is_empty:
            continue

        selected = bid == st.session_state.selected_id
        color    = b.get("color", "#4A90D9")
        # Use rgba() — Plotly 6+ does not accept 8-char hex (#RRGGBBaa)
        fill_alpha   = 0.87 if selected else 0.60
        fill_rgba    = hex_to_rgba(color, fill_alpha)
        line_width   = 3 if selected else 1.5

        hover_txt = (
            f"<b>{b['name']}</b><br>"
            f"Category: {b['category']}<br>"
            f"Shape: {b['shape']}<br>"
            f"Area: {poly.area:.1f} m²"
        )
        _add_polygon_trace(fig, poly,
                           fill=fill_rgba,
                           line_color=color,
                           line_width=line_width,
                           name=b["name"], hover=hover_txt)

        # Safety buffer
        if st.session_state.show_safety_zones:
            buf = poly.buffer(st.session_state.safety_margin)
            _add_polygon_trace(fig, buf,
                               fill=hex_to_rgba(color, 0.09),
                               line_color=hex_to_rgba(color, 0.33),
                               line_width=1)

        # Label
        cx_, cy_ = poly.centroid.x, poly.centroid.y
        fig.add_trace(go.Scatter(
            x=[cx_], y=[cy_], mode="text",
            text=[b["name"]],
            textfont=dict(size=10, color="#1a1a1a", family="monospace"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Layout ─────────────────────────────────────────────
    fig.update_layout(
        plot_bgcolor="#F5F8FC",
        paper_bgcolor="#F5F8FC",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(showgrid=True, gridcolor="#DDE6F0", zeroline=False,
                   scaleanchor="y", scaleratio=1, title="X (m)"),
        yaxis=dict(showgrid=True, gridcolor="#DDE6F0", zeroline=False,
                   title="Y (m)"),
        dragmode="pan",
        height=640,
        clickmode="event",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# DRAG-AND-DROP BOUNDARY EDITOR  (HTML component)
# ─────────────────────────────────────────────────────────────
BOUNDARY_EDITOR_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: monospace; background: #F5F8FC; }
  #wrap { position: relative; width: 100%; }
  canvas { display: block; cursor: crosshair; border: 2px solid #2C3E50;
           border-radius: 6px; background: #fff; }
  #toolbar {
    display: flex; gap: 8px; padding: 8px;
    flex-wrap: wrap; background: #EEF2F7;
    border-radius: 6px; margin-bottom: 8px;
  }
  button {
    padding: 5px 12px; border: none; border-radius: 4px;
    cursor: pointer; font-size: 12px; font-family: monospace;
  }
  .btn-primary { background: #4A90D9; color: #fff; }
  .btn-danger  { background: #E74C3C; color: #fff; }
  .btn-neutral { background: #95A5A6; color: #fff; }
  .btn-green   { background: #27AE60; color: #fff; }
  #status { font-size: 11px; color: #555; padding: 4px 8px;
            background: #fff; border-radius: 4px; min-width: 200px;
            display:flex; align-items:center; }
  #modeLabel { font-weight: bold; color: #4A90D9; margin-right: 6px; }
  label { font-size:11px; color:#333; display:flex; align-items:center; gap:4px; }
  input[type=range] { width:80px; }
</style>
</head>
<body>
<div id="toolbar">
  <button class="btn-primary" onclick="setMode('move')">✋ Move vertex</button>
  <button class="btn-primary" onclick="setMode('add')">➕ Add vertex</button>
  <button class="btn-danger"  onclick="setMode('delete')">🗑 Delete vertex</button>
  <button class="btn-green"   onclick="setMode('freehand')">✏️ Freehand draw</button>
  <button class="btn-neutral" onclick="smooth()">〜 Smooth</button>
  <button class="btn-neutral" onclick="resetDefault()">↩ Reset</button>
  <button class="btn-danger"  onclick="clearAll()">✕ Clear</button>
  <label>Grid: <input type="range" id="gridSlider" min="0" max="20" value="5"
         oninput="gridSize=+this.value;draw()"> <span id="gridVal">5</span>m</label>
  <div id="status"><span id="modeLabel">MOVE</span><span id="statusTxt">Drag a vertex to reshape the boundary</span></div>
</div>
<div id="wrap"><canvas id="c"></canvas></div>

<script>
// ── State ──────────────────────────────────────────────────
const WORLD_W = 140, WORLD_H = 110;  // metres visible
let verts = INIT_VERTS;              // injected by Python
let mode = 'move';
let dragging = -1;
let freehand = false;
let fhPoints = [];
let gridSize = 5;
let W, H, scale, offX, offY;

// ── Canvas setup ───────────────────────────────────────────
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');

function resize() {
  const wrap = document.getElementById('wrap');
  W = wrap.clientWidth;
  H = Math.round(W * WORLD_H / WORLD_W);
  canvas.width  = W;
  canvas.height = H;
  scale = W / WORLD_W;
  offX  = 0; offY = 0;
  document.getElementById('gridSlider').oninput();
  draw();
}

window.addEventListener('resize', resize);
resize();

// ── Coordinate helpers ─────────────────────────────────────
function toCanvas(wx, wy) {
  return [wx * scale, H - wy * scale];
}
function toWorld(cx, cy) {
  return [cx / scale, (H - cy) / scale];
}
function snapW(v) {
  if (gridSize <= 0) return v;
  return Math.round(v / gridSize) * gridSize;
}
function closestVertex(cx, cy, thresh=14) {
  let best = -1, bd = Infinity;
  verts.forEach(([wx, wy], i) => {
    const [px, py] = toCanvas(wx, wy);
    const d = Math.hypot(cx-px, cy-py);
    if (d < bd && d < thresh) { bd = d; best = i; }
  });
  return best;
}

// ── Draw ───────────────────────────────────────────────────
function draw() {
  ctx.clearRect(0, 0, W, H);

  // grid
  if (gridSize > 0) {
    ctx.strokeStyle = '#DDE6F0';
    ctx.lineWidth = 0.5;
    for (let gx = 0; gx <= WORLD_W; gx += gridSize) {
      const [px] = toCanvas(gx, 0);
      ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, H); ctx.stroke();
    }
    for (let gy = 0; gy <= WORLD_H; gy += gridSize) {
      const [, py] = toCanvas(0, gy);
      ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke();
    }
  }

  // site fill
  if (verts.length >= 3) {
    ctx.beginPath();
    verts.forEach(([wx, wy], i) => {
      const [px, py] = toCanvas(wx, wy);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fillStyle = 'rgba(74,144,217,0.12)';
    ctx.fill();
    ctx.strokeStyle = '#2C3E50';
    ctx.lineWidth = 2;
    ctx.setLineDash([8, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // freehand preview
  if (fhPoints.length > 1) {
    ctx.beginPath();
    fhPoints.forEach(([wx, wy], i) => {
      const [px, py] = toCanvas(wx, wy);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    });
    ctx.strokeStyle = '#E74C3C';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // vertices
  verts.forEach(([wx, wy], i) => {
    const [px, py] = toCanvas(wx, wy);
    ctx.beginPath();
    ctx.arc(px, py, i === dragging ? 9 : 6, 0, 2*Math.PI);
    ctx.fillStyle   = i === dragging ? '#E74C3C' : '#4A90D9';
    ctx.strokeStyle = '#fff';
    ctx.lineWidth   = 2;
    ctx.fill(); ctx.stroke();
    // index label
    ctx.fillStyle = '#2C3E50';
    ctx.font = '10px monospace';
    ctx.fillText(i, px+8, py-6);
  });

  // axis labels
  ctx.fillStyle = '#999'; ctx.font = '10px monospace';
  for (let gx = 0; gx <= WORLD_W; gx += gridSize*2) {
    const [px] = toCanvas(gx, 0);
    ctx.fillText(gx, px+2, H-4);
  }
  for (let gy = 0; gy <= WORLD_H; gy += gridSize*2) {
    const [, py] = toCanvas(0, gy);
    ctx.fillText(gy, 2, py-2);
  }
}

// ── Mode ───────────────────────────────────────────────────
const modeMsg = {
  move:     'Drag a vertex to reshape the boundary',
  add:      'Click anywhere on the canvas to add a vertex',
  delete:   'Click a vertex to remove it',
  freehand: 'Click and drag to draw a freehand outline — release to finish',
};
function setMode(m) {
  mode = m;
  freehand = false; fhPoints = [];
  document.getElementById('modeLabel').textContent = m.toUpperCase();
  document.getElementById('statusTxt').textContent  = modeMsg[m];
  draw();
}

// ── Smoothing (Chaikin) ────────────────────────────────────
function smooth() {
  if (verts.length < 4) return;
  const out = [];
  const n = verts.length;
  for (let i = 0; i < n; i++) {
    const [x0,y0] = verts[i], [x1,y1] = verts[(i+1)%n];
    out.push([0.75*x0+0.25*x1, 0.75*y0+0.25*y1]);
    out.push([0.25*x0+0.75*x1, 0.25*y0+0.75*y1]);
  }
  verts = out;
  push();
}

function clearAll()    { verts = []; push(); }
function resetDefault(){ verts = DEFAULT_VERTS.map(v=>[...v]); push(); }

// ── Push to Streamlit ──────────────────────────────────────
function push() {
  draw();
  window.parent.postMessage(
    { type: 'boundary_update', verts: verts },
    '*'
  );
}

// ── Mouse events ───────────────────────────────────────────
function getPos(e) {
  const r = canvas.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}

canvas.addEventListener('mousedown', e => {
  const [cx, cy] = getPos(e);
  const [wx, wy] = toWorld(cx, cy);

  if (mode === 'move') {
    dragging = closestVertex(cx, cy);
  } else if (mode === 'add') {
    // Insert after nearest edge
    const sx = snapW(wx), sy = snapW(wy);
    if (verts.length < 2) { verts.push([sx, sy]); push(); return; }
    let best = 0, bd = Infinity;
    for (let i = 0; i < verts.length; i++) {
      const [ax,ay] = verts[i], [bx,by] = verts[(i+1)%verts.length];
      const mx=(ax+bx)/2, my=(ay+by)/2;
      const d = Math.hypot(sx-mx, sy-my);
      if (d < bd) { bd=d; best=i; }
    }
    verts.splice(best+1, 0, [sx, sy]);
    push();
  } else if (mode === 'delete') {
    const idx = closestVertex(cx, cy);
    if (idx >= 0 && verts.length > 3) { verts.splice(idx,1); push(); }
  } else if (mode === 'freehand') {
    freehand = true; fhPoints = [[wx, wy]];
  }
});

canvas.addEventListener('mousemove', e => {
  const [cx, cy] = getPos(e);
  const [wx, wy] = toWorld(cx, cy);

  if (mode === 'move' && dragging >= 0) {
    verts[dragging] = [snapW(wx), snapW(wy)];
    draw();
  } else if (mode === 'freehand' && freehand) {
    fhPoints.push([wx, wy]);
    draw();
  }
});

canvas.addEventListener('mouseup', e => {
  if (mode === 'move' && dragging >= 0) {
    dragging = -1; push();
  } else if (mode === 'freehand' && freehand) {
    freehand = false;
    if (fhPoints.length > 4) {
      // Decimate to ~40 points
      const step = Math.max(1, Math.floor(fhPoints.length / 40));
      verts = fhPoints.filter((_,i) => i % step === 0);
    }
    fhPoints = [];
    push();
  }
});

// Touch support
canvas.addEventListener('touchstart', e => {
  e.preventDefault();
  const t = e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousedown', {clientX:t.clientX, clientY:t.clientY}));
}, {passive:false});
canvas.addEventListener('touchmove', e => {
  e.preventDefault();
  const t = e.touches[0];
  canvas.dispatchEvent(new MouseEvent('mousemove', {clientX:t.clientX, clientY:t.clientY}));
}, {passive:false});
canvas.addEventListener('touchend', e => {
  canvas.dispatchEvent(new MouseEvent('mouseup', {}));
}, {passive:false});

// Grid slider label
document.getElementById('gridSlider').oninput = function() {
  gridSize = +this.value;
  document.getElementById('gridVal').textContent = gridSize;
  draw();
};
</script>
</body>
</html>
"""


def _inject_boundary_editor() -> str:
    """Return the HTML with current vertices injected."""
    verts_js = json.dumps(st.session_state.site_vertices)
    html = BOUNDARY_EDITOR_HTML.replace("INIT_VERTS", verts_js)
    html = html.replace("DEFAULT_VERTS", verts_js)
    return html


# ─────────────────────────────────────────────────────────────
# UTILISATION STATS
# ─────────────────────────────────────────────────────────────
def utilisation_stats() -> dict:
    site = site_polygon()
    site_area = site.area if not site.is_empty else 0.0

    polys = [building_polygon(b) for b in st.session_state.buildings.values()]
    polys = [p for p in polys if not p.is_empty]
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
# SIDEBAR
# ─────────────────────────────────────────────────────────────
def render_sidebar() -> None:
    st.sidebar.markdown(
        "<h2 style='margin-bottom:0;color:#fff'>🏗️ Site Planner</h2>"
        "<p style='font-size:.75rem;color:#8BAACC;margin-top:2px'>v2.0 · Construction Layout Tool</p>",
        unsafe_allow_html=True,
    )
    st.sidebar.divider()

    st.sidebar.subheader("🛡️ Safety Parameters")
    st.session_state.safety_margin = st.sidebar.slider(
        "Clearance between structures (m)", 0.0, 10.0,
        st.session_state.safety_margin, 0.5,
        help="Minimum gap enforced between any two structures")
    st.session_state.boundary_threshold = st.sidebar.slider(
        "Boundary setback (m)", 0.0, 15.0,
        st.session_state.boundary_threshold, 0.5,
        help="Structures must be set back this far from the site boundary")
    st.session_state.snap_grid = st.sidebar.select_slider(
        "Snap-to-grid (m)", [0.0, 0.5, 1.0, 2.0, 5.0],
        st.session_state.snap_grid,
        help="0 = free placement")
    st.sidebar.divider()

    st.sidebar.subheader("👁️ Display")
    st.session_state.show_safety_zones = st.sidebar.toggle(
        "Safety buffer zones", st.session_state.show_safety_zones)
    st.session_state.show_utilisation = st.sidebar.toggle(
        "Utilisation panel", st.session_state.show_utilisation)
    st.sidebar.divider()

    st.sidebar.subheader("💾 Save / Load")
    st.sidebar.download_button(
        "📥 Export layout JSON", data=export_state(),
        file_name="site_layout.json", mime="application/json",
        use_container_width=True,
        help="Download current layout as a JSON file")
    up = st.sidebar.file_uploader("📂 Import JSON", type="json",
                                   label_visibility="visible")
    if up:
        try:
            import_state(up.read().decode())
            st.success("Layout imported successfully.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Import failed: {e}")

    st.sidebar.divider()

    # Stats summary
    s = utilisation_stats()
    m1, m2, m3 = st.sidebar.columns(3)
    m1.metric("Structures", s["n_buildings"])
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
                     index=list(CATEGORY_COLORS).index(b.get("category", "Office / Admin")))
        color    = st.color_picker("Colour",
                     value=b.get("color", CATEGORY_COLORS[category]))

    with col2:
        shape  = st.selectbox("Shape", SHAPE_TYPES,
                    index=SHAPE_TYPES.index(b.get("shape", "Rectangle")))
        angle  = st.slider("Rotation (°)", -180, 180, int(b.get("angle", 0)), 5)
        notes  = st.text_area("Notes", value=b.get("notes", ""), height=68)

    st.divider()
    g = st.session_state.snap_grid
    params: dict = {}

    # ── Shape params ───────────────────────────────────────
    if shape == "Rectangle":
        c1, c2, c3, c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X (m)", value=float(b.get("x", 10)), step=max(g,0.1)), g)
        params["y"]      = snap(c2.number_input("Y (m)", value=float(b.get("y", 10)), step=max(g,0.1)), g)
        params["width"]  = snap(c3.number_input("Width (m)",  value=float(b.get("width",  20)), min_value=1.0, step=max(g,0.1)), g)
        params["height"] = snap(c4.number_input("Height (m)", value=float(b.get("height", 15)), min_value=1.0, step=max(g,0.1)), g)

    elif shape == "L-Shape":
        c1,c2,c3,c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X",       value=float(b.get("x",10)),     step=max(g,0.1)), g)
        params["y"]      = snap(c2.number_input("Y",       value=float(b.get("y",10)),     step=max(g,0.1)), g)
        params["width"]  = snap(c3.number_input("Width",   value=float(b.get("width",20)), min_value=2.0, step=max(g,0.1)), g)
        params["height"] = snap(c4.number_input("Height",  value=float(b.get("height",15)),min_value=2.0, step=max(g,0.1)), g)
        c5,c6 = st.columns(2)
        params["stem_w"] = snap(c5.number_input("Stem W (m)", value=float(b.get("stem_w",10)), min_value=1.0, step=max(g,0.1)), g)
        params["stem_h"] = snap(c6.number_input("Stem H (m)", value=float(b.get("stem_h",8)),  min_value=1.0, step=max(g,0.1)), g)

    elif shape == "T-Shape":
        c1,c2,c3,c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X",        value=float(b.get("x",10)),     step=max(g,0.1)), g)
        params["y"]      = snap(c2.number_input("Y",        value=float(b.get("y",10)),     step=max(g,0.1)), g)
        params["width"]  = snap(c3.number_input("Width",    value=float(b.get("width",30)), min_value=3.0, step=max(g,0.1)), g)
        params["height"] = snap(c4.number_input("Height",   value=float(b.get("height",20)),min_value=2.0, step=max(g,0.1)), g)
        params["cap_h"]  = snap(st.number_input("Cap height (m)", value=float(b.get("cap_h",8)), min_value=1.0, step=max(g,0.1)), g)

    elif shape == "Hexagon":
        c1,c2,c3 = st.columns(3)
        params["x"]      = snap(c1.number_input("Centre X", value=float(b.get("x",20)), step=max(g,0.1)), g)
        params["y"]      = snap(c2.number_input("Centre Y", value=float(b.get("y",20)), step=max(g,0.1)), g)
        params["radius"] = snap(c3.number_input("Radius (m)", value=float(b.get("radius",8)), min_value=1.0, step=max(g,0.1)), g)

    elif shape == "Circle":
        c1,c2,c3 = st.columns(3)
        params["x"]      = snap(c1.number_input("Centre X", value=float(b.get("x",20)), step=max(g,0.1)), g)
        params["y"]      = snap(c2.number_input("Centre Y", value=float(b.get("y",20)), step=max(g,0.1)), g)
        params["radius"] = snap(c3.number_input("Radius (m)", value=float(b.get("radius",8)), min_value=1.0, step=max(g,0.1)), g)
        st.caption(f"Area ≈ {math.pi * b.get('radius',8)**2:.1f} m²")

    elif shape == "Semicircle":
        c1,c2,c3 = st.columns(3)
        params["x"]          = snap(c1.number_input("Centre X",    value=float(b.get("x",20)),           step=max(g,0.1)), g)
        params["y"]          = snap(c2.number_input("Centre Y",    value=float(b.get("y",20)),           step=max(g,0.1)), g)
        params["radius"]     = snap(c3.number_input("Radius (m)",  value=float(b.get("radius",10)),      min_value=1.0, step=max(g,0.1)), g)
        params["flat_angle"] = st.slider("Flat-edge direction (°)", 0, 360,
                                          int(b.get("flat_angle", 0)), 15,
                                          help="0° = flat on bottom, 90° = flat on left")

    elif shape == "Road":
        st.info("Enter waypoints as X,Y pairs (one per line). Minimum 2 points.")
        default_wp = b.get("waypoints", [(10,10),(40,10),(40,40)])
        raw_wp = st.text_area(
            "Waypoints (X,Y per line)",
            value="\n".join(f"{p[0]},{p[1]}" for p in default_wp),
            height=100,
        )
        parsed_wp: list = []
        for line in raw_wp.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_wp.append((float(px_.strip()), float(py_.strip())))
            except ValueError:
                pass
        params["waypoints"]  = parsed_wp
        params["road_width"] = st.slider("Road width (m)", 2.0, 20.0,
                                          float(b.get("road_width", 5.0)), 0.5)
        params["x"] = parsed_wp[0][0] if parsed_wp else 0
        params["y"] = parsed_wp[0][1] if parsed_wp else 0

    elif shape == "Custom Polygon":
        st.info("Enter X,Y pairs (one per line).")
        default_pts = b.get("custom_pts", [(10,10),(30,10),(30,25),(10,25)])
        raw_pts = st.text_area(
            "Vertices (X,Y per line)",
            value="\n".join(f"{p[0]},{p[1]}" for p in default_pts),
            height=110,
        )
        parsed_pts: list = []
        for line in raw_pts.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_pts.append((float(px_.strip()), float(py_.strip())))
            except ValueError:
                pass
        params["custom_pts"] = parsed_pts
        params["x"] = parsed_pts[0][0] if parsed_pts else 0
        params["y"] = parsed_pts[0][1] if parsed_pts else 0

    params.update(shape=shape, angle=float(angle),
                  name=name, category=category, color=color, notes=notes)

    # ── Preview area ──────────────────────────────────────
    preview = building_polygon(params)
    if not preview.is_empty:
        bb = preview.bounds
        col_prev, col_bnd, col_clr = st.columns(3)
        col_prev.caption(
            f"**Area:** {preview.area:.1f} m²  ·  "
            f"**Box:** {bb[2]-bb[0]:.1f} × {bb[3]-bb[1]:.1f} m"
        )
        # Live boundary & clearance feedback
        dummy_id = existing_id or "__preview__"
        bnd_ok = check_boundary(preview)
        clr_hits = check_collisions(dummy_id, preview)
        col_bnd.caption("Boundary: " + ("✅ Inside setback" if bnd_ok else "⚠️ Breaches setback"))
        col_clr.caption("Clearance: " + ("✅ Clear" if not clr_hits else f"⚠️ Conflicts: {', '.join(clr_hits)}"))

    # ── Save / Cancel ────────────────────────────────────
    sc, cc, *_ = st.columns([1, 1, 3])
    if sc.button("💾 Save" if is_edit else "➕ Place", type="primary",
                 use_container_width=True):
        bid  = existing_id or str(uuid.uuid4())[:8]
        poly = building_polygon(params)

        warns = []
        hits  = check_collisions(bid, poly)
        if hits:
            warns.append(f"⚠️ Clearance violated with: {', '.join(hits)}")
        if not check_boundary(poly):
            warns.append("⚠️ Breaches boundary setback.")

        if warns and not st.session_state.get("_force"):
            for w in warns:
                st.warning(w)
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
# BOUNDARY EDITOR PANEL
# ─────────────────────────────────────────────────────────────
def render_boundary_panel() -> None:
    st.subheader("🗺️ Edit Site Boundary")

    tab_canvas, tab_text, tab_preset = st.tabs(
        ["🖱️ Drag & Draw Canvas", "⌨️ Type Coordinates", "📐 Presets"]
    )

    # ── Tab 1 : interactive canvas ─────────────────────────
    with tab_canvas:
        st.info(
            "**Move vertex** — drag a blue dot  ·  "
            "**Add vertex** — click on canvas  ·  "
            "**Freehand** — click-drag to draw a curved outline freely  ·  "
            "**Smooth** — rounds sharp corners"
        )

        # Receive postMessage from the iframe via a hidden text input trick:
        # We display the canvas, then read back via a text_area that JS fills.
        # Streamlit ↔ iframe: we use st.session_state + a query-param round-trip.

        html_src = _inject_boundary_editor()
        components.html(html_src, height=560, scrolling=False)

        st.divider()
        st.caption("Paste updated vertex JSON here after editing (copy from browser console if needed), or use the text tab for direct input.")

        raw_json = st.text_area(
            "Paste vertex JSON array (optional override)",
            value="", height=60, label_visibility="collapsed",
            placeholder='[[0,0],[100,0],[100,80],[0,80]]',
        )
        if raw_json.strip():
            try:
                parsed = json.loads(raw_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 3:
                    st.session_state.site_vertices = [tuple(p) for p in parsed]
                    st.success(f"Applied {len(parsed)} vertices.")
                    st.rerun()
            except Exception as e:
                st.error(f"Invalid JSON: {e}")

    # ── Tab 2 : text input ────────────────────────────────
    with tab_text:
        raw = st.text_area(
            "Vertices (X,Y per line)",
            value="\n".join(f"{p[0]},{p[1]}" for p in st.session_state.site_vertices),
            height=220,
        )
        parsed_text: list = []
        for line in raw.strip().splitlines():
            try:
                px_, py_ = line.split(",")
                parsed_text.append((float(px_.strip()), float(py_.strip())))
            except ValueError:
                pass
        if len(parsed_text) >= 3:
            area = Polygon(parsed_text).area
            st.caption(f"Area: **{area:.1f} m²** · {len(parsed_text)} vertices")
        if st.button("✅ Apply", type="primary"):
            if len(parsed_text) < 3:
                st.error("Need ≥ 3 valid points.")
            else:
                st.session_state.site_vertices = parsed_text
                st.session_state.edit_mode = "view"
                st.rerun()

    # ── Tab 3 : presets ───────────────────────────────────
    with tab_preset:
        presets: dict[str, list] = {
            "Default (irregular)": list(DEFAULT_BOUNDARY),
            "Rectangle 120×80":   [(0,0),(120,0),(120,80),(0,80)],
            "Large square 150×150": [(0,0),(150,0),(150,150),(0,150)],
            "L-shaped":           [(0,0),(100,0),(100,40),(60,40),(60,80),(0,80)],
            "T-shaped":           [(20,0),(80,0),(80,40),(100,40),(100,60),(80,60),
                                   (80,90),(20,90),(20,60),(0,60),(0,40),(20,40)],
            "Trapezoid":          [(10,0),(110,0),(120,80),(0,80)],
            "Pentagon site":      [(50,0),(100,30),(85,90),(15,90),(0,30)],
            "Oval (approx)":      [
                (50+40*math.cos(2*math.pi*i/24),
                 40+28*math.sin(2*math.pi*i/24))
                for i in range(24)
            ],
        }
        choice = st.selectbox("Select preset", list(presets))
        prev   = Polygon(presets[choice])
        st.caption(f"Area: {prev.area:.1f} m² · {len(presets[choice])} vertices")
        if st.button("Load preset", type="primary"):
            st.session_state.site_vertices = presets[choice]
            st.session_state.edit_mode = "view"
            st.rerun()

    sc, cc = st.columns([1, 1])
    if cc.button("✕ Cancel", use_container_width=True):
        st.session_state.edit_mode = "view"
        st.rerun()


# ─────────────────────────────────────────────────────────────
# STRUCTURE TABLE
# ─────────────────────────────────────────────────────────────
def render_table() -> None:
    if not st.session_state.buildings:
        st.markdown(
            "<div style='text-align:center;padding:2rem;background:#F8FAFD;"
            "border-radius:10px;border:1.5px dashed #BDD0E5;color:#7A9BB5'>"
            "<p style='font-size:1.5rem;margin:0'>🏗️</p>"
            "<p style='margin:4px 0 0'>No structures yet — click <b>➕ Add Structure</b> above.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    rows = []
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        is_selected = "⭐" if bid == st.session_state.selected_id else ""
        rows.append({
            "":            is_selected,
            "Name":        b["name"],
            "Category":    b["category"],
            "Shape":       b["shape"],
            "Area (m²)":   f"{poly.area:.1f}",
            "Rotation":    f"{b.get('angle',0):.0f}°",
            "Boundary":    "✅" if check_boundary(poly) else "⚠️",
            "Clearance":   "✅" if not check_collisions(bid, poly) else "⚠️",
        })

    st.dataframe(pd.DataFrame(rows),
                 use_container_width=True, height=200, hide_index=True)

    all_names = {b["name"]: bid for bid, b in st.session_state.buildings.items()}
    sc, ec, dc = st.columns([3, 1, 1])
    sel = sc.selectbox("Select structure", ["— select —"] + list(all_names),
                        label_visibility="collapsed")
    if sel != "— select —":
        sid = all_names[sel]
        if ec.button("✏️ Edit", use_container_width=True):
            st.session_state.selected_id = sid
            st.session_state.edit_mode   = "edit_building"
            st.rerun()
        if dc.button("🗑️ Delete", use_container_width=True, type="secondary"):
            del st.session_state.buildings[sid]
            if st.session_state.selected_id == sid:
                st.session_state.selected_id = None
            st.rerun()


# ─────────────────────────────────────────────────────────────
# UTILISATION PANEL
# ─────────────────────────────────────────────────────────────
def render_utilisation() -> None:
    s = utilisation_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Site Area",   f"{s['site_area']:.0f} m²")
    c2.metric("Built Area",  f"{s['inside_area']:.0f} m²")
    c3.metric("Free Area",   f"{s['free_area']:.0f} m²")
    c4.metric("Utilisation", f"{s['utilisation_pct']:.1f}%")

    pct = min(s["utilisation_pct"] / 100, 1.0)
    if pct > 0.9:
        bar_color, status_icon, status_text = "#E74C3C", "🔴", "Site nearly full — consider expanding the boundary"
    elif pct > 0.75:
        bar_color, status_icon, status_text = "#E07B39", "🟡", "Getting busy — monitor clearances"
    else:
        bar_color, status_icon, status_text = "#27AE60", "🟢", "Plenty of space available"

    st.markdown(
        f"""
        <div style="margin:6px 0 2px">
          <div style="background:#DDE6F0;border-radius:6px;height:12px;overflow:hidden">
            <div style="background:{bar_color};width:{pct*100:.1f}%;height:100%;
                        border-radius:6px;transition:width .4s ease"></div>
          </div>
          <p style="font-size:.78rem;color:#555;margin:4px 0 0">
            {status_icon} {s['n_buildings']} structure(s) placed &nbsp;·&nbsp; {status_text}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main() -> None:
    render_sidebar()

    # ── Page header ───────────────────────────────────────
    st.markdown("## 🏗️ Construction Site Planner")

    # ── Toolbar ───────────────────────────────────────────
    t1, t2, t3, t4 = st.columns([3, 3, 2, 2])
    if t1.button("➕ Add Structure", type="primary", use_container_width=True):
        st.session_state.edit_mode   = "add"
        st.session_state.selected_id = None
        st.session_state.pop("_force", None)
    if t2.button("🗺️ Edit Boundary", use_container_width=True):
        st.session_state.edit_mode = "edit_boundary"

    # Destructive actions — require a second click to confirm
    if t3.button("🗑️ Clear All", use_container_width=True):
        st.session_state["_confirm_clear"] = True
    if t4.button("🔄 Reset", use_container_width=True):
        st.session_state["_confirm_reset"] = True

    if st.session_state.pop("_confirm_clear", False):
        col_y, col_n = st.columns(2)
        st.warning("Remove all structures from the canvas?")
        if col_y.button("Yes, clear all", type="primary", use_container_width=True):
            st.session_state.buildings   = {}
            st.session_state.selected_id = None
            st.rerun()
        if col_n.button("Cancel", use_container_width=True):
            st.rerun()

    if st.session_state.pop("_confirm_reset", False):
        col_y, col_n = st.columns(2)
        st.warning("Reset everything — structures **and** boundary?")
        if col_y.button("Yes, reset everything", type="primary", use_container_width=True):
            for k in ["buildings", "site_vertices", "selected_id", "edit_mode"]:
                del st.session_state[k]
            st.rerun()
        if col_n.button("Cancel", use_container_width=True):
            st.rerun()

    # ── Active panel ──────────────────────────────────────
    panel_open = False
    if st.session_state.edit_mode == "add":
        st.divider()
        render_add_edit_form()
        panel_open = True
    elif st.session_state.edit_mode == "edit_building" and st.session_state.selected_id:
        st.divider()
        render_add_edit_form(st.session_state.selected_id)
        panel_open = True
    elif st.session_state.edit_mode == "edit_boundary":
        st.divider()
        render_boundary_panel()
        panel_open = True

    if panel_open:
        st.divider()

    # ── Utilisation ───────────────────────────────────────
    if st.session_state.show_utilisation:
        render_utilisation()
        st.divider()

    # ── Canvas ────────────────────────────────────────────
    in_bnd_edit = st.session_state.edit_mode == "edit_boundary"
    st.plotly_chart(build_figure(boundary_edit_mode=in_bnd_edit),
                    use_container_width=True,
                    config={
                        "scrollZoom": True,
                        "displayModeBar": True,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                        "toImageButtonOptions": {
                            "format": "png",
                            "filename": "site_layout",
                            "scale": 2,
                        },
                    })

    # ── Structure table ───────────────────────────────────
    st.subheader("📋 Structures")
    render_table()


if __name__ == "__main__":
    main()
