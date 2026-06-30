"""
Construction Site Planner  ·  v6.0 (Custom Components v2, Advanced Geometry)
─────────────────────────────────────────────────────────────────────────────
"""

import json
import copy
import streamlit as st

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Site Planner", page_icon="🏗️", layout="wide")

# ─────────────────────────────────────────────────────────────
# CANVAS COMPONENT — HTML / CSS / JS, inlined as plain strings
# ─────────────────────────────────────────────────────────────
_CANVAS_HTML = """
  <div id="toolbar">
    <div class="group">
      <label>Add shape:</label>
      <button class="shape-btn" draggable="true" data-shape="rectangle"><span class="shape-icon">&#9646;</span>Rect</button>
      <button class="shape-btn" draggable="true" data-shape="circle"><span class="shape-icon">&#9679;</span>Circle</button>
      <button class="shape-btn" draggable="true" data-shape="triangle"><span class="shape-icon">&#9650;</span>Tri</button>
      <button class="shape-btn" draggable="true" data-shape="l_shape"><span class="shape-icon">&#8990;</span>L-Shape</button>
    </div>
    <div class="group" style="margin-left: 10px; padding-left: 10px; border-left: 1px solid #D4DFEA;">
      <label><input type="checkbox" id="snapGrid"> Grid Snap</label>
      <button class="shape-btn" id="clearBtn" style="color: #C0392B;">Clear All</button>
    </div>
    <div class="group" style="margin-left: auto;">
      <label>Site boundary:</label>
      <select id="boundarySelect">
        <option value="rectangle">Rectangle</option>
        <option value="l_shape">L-Shape</option>
        <option value="pentagon">Pentagon</option>
        <option value="hexagon">Hexagon</option>
        <option value="trapezoid">Trapezoid</option>
      </select>
      <label>Sides:</label>
      <input type="number" id="boundarySides" min="3" max="20" step="1" style="width:54px" />
    </div>
  </div>
  <div class="hint">Drag a shape onto the site. Select a shape to reveal its handles: drag corner squares to resize symmetrically; drag the top circle handle to rotate.</div>

  <div id="main">
    <div id="canvasWrap">
      <svg id="canvas" viewBox="0 0 200 130" preserveAspectRatio="xMidYMid meet"></svg>
    </div>
    <div id="side">
      <h4>Site stats</h4>
      <div class="stats-row" id="statsRow"></div>
      <h4>Buildings</h4>
      <div id="bldList"></div>
    </div>
  </div>
"""

_CANVAS_CSS = """
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
  body { padding: 10px; background: #F7F9FC; color: #1F2D3D; }

  #toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 8px; }
  .group { display: flex; align-items: center; gap: 6px; }
  .group label { font-size: 12px; font-weight: 600; color: #4A5A6A; cursor: pointer; }

  .shape-btn {
    display: flex; align-items: center; gap: 4px;
    border: 1px solid #C7D4E2; background: #fff; border-radius: 6px;
    padding: 5px 8px; font-size: 12px; cursor: pointer; user-select: none;
    transition: box-shadow .15s, transform .15s;
  }
  .shape-btn:hover { box-shadow: 0 2px 6px rgba(0,0,0,.12); transform: translateY(-1px); }
  .shape-btn:active { transform: translateY(0); }
  .shape-icon { font-size: 13px; }

  select, input[type="text"], input[type="number"] {
    border: 1px solid #C7D4E2; border-radius: 6px; padding: 4px 7px; font-size: 12.5px;
  }

  .hint { font-size: 11.5px; color: #8094A8; margin-bottom: 8px; }

  #main { display: flex; gap: 12px; align-items: flex-start; }

  #canvasWrap {
    flex: 1 1 auto; border: 1px solid #D4DFEA; border-radius: 10px; background: #fff;
    min-width: 0; position: relative; overflow: hidden;
  }
  svg#canvas { width: 100%; height: auto; display: block; touch-action: none; }

  #side {
    flex: 0 0 260px; max-width: 260px;
    border: 1px solid #D4DFEA; border-radius: 10px; background: #fff; padding: 10px;
    max-height: 480px; overflow-y: auto;
  }
  #side h4 { margin: 0 0 8px; font-size: 12.5px; color: #4A5A6A; }

  .stats-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
  .stat {
    background: #F0F4FA; border-left: 3px solid #4A90D9; border-radius: 6px;
    padding: 5px 8px; font-size: 11px; flex: 1 1 70px;
  }
  .stat b { display: block; font-size: 13px; }

  .bld-row {
    border: 1px solid #E3EAF2; border-radius: 8px; padding: 7px 8px; margin-bottom: 7px;
  }
  .bld-row.selected { border-color: #4A90D9; background: #F3F8FE; }
  .bld-row .top { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
  
  .color-picker { width: 22px; height: 24px; padding: 0; border: 1px solid #C7D4E2; border-radius: 4px; cursor: pointer; flex: none; background: none; }
  .bld-row input[type="text"] { flex: 1 1 auto; min-width: 0; font-size: 12px; }
  
  .icon-btn { border: none; background: #F0F4FA; color: #4A5A6A; border-radius: 4px; width: 24px; height: 24px; cursor: pointer; font-size: 13px; flex: none; display: flex; align-items: center; justify-content: center; }
  .icon-btn:hover { background: #E3EAF2; }
  .icon-btn.del { background: #FCEAEA; color: #C0392B; }
  .icon-btn.del:hover { background: #FAD4D4; }

  .bld-row .meta { font-size: 10.5px; color: #8094A8; margin-bottom: 5px; }
  .warn-badge { color: #E74C3C; font-size: 10.5px; font-weight: 600; }
  .empty-list { font-size: 12px; color: #95A5B5; text-align: center; padding: 14px 4px; }
"""

_CANVAS_JS = """
export default function(component) {
const { data, parentElement, setStateValue } = component;

// PREVENT STREAMLIT RERUN GLITCHES
if (window.__canvas_initialized__) return;
window.__canvas_initialized__ = true;

// ─────────────────────────────────────────────────────────────
// CONSTANTS & GEOMETRY MATH
// ─────────────────────────────────────────────────────────────
const WORLD_W = 200, WORLD_H = 130;
const MIN_SIZE = 4;
let SNAP = 1; // 1 = smooth, 5 = rigid grid

function snap(v) { return Math.round(v / SNAP) * SNAP; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function getBBox(pts) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for(const [x,y] of pts) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return {minX, minY, maxX, maxY};
}

// Math rotation for points (allows accurate collision on rotated shapes)
function rotatePt([px, py], cx, cy, deg) {
  if (!deg) return [px, py];
  const rad = deg * Math.PI / 180;
  const cos = Math.cos(rad), sin = Math.sin(rad);
  const dx = px - cx, dy = py - cy;
  return [cx + dx * cos - dy * sin, cy + dx * sin + dy * cos];
}

// Accurate Polygon Intersections (Separating Axis + Line Intersect)
function pointInPolygon(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function segmentsIntersect(p1, p2, p3, p4) {
  const ccw = (a, b, c) => (c[1]-a[1])*(b[0]-a[0]) > (b[1]-a[1])*(c[0]-a[0]);
  return ccw(p1,p3,p4) !== ccw(p2,p3,p4) && ccw(p1,p2,p3) !== ccw(p1,p2,p4);
}

function polysOverlap(ptsA, ptsB) {
  const bbA = getBBox(ptsA), bbB = getBBox(ptsB);
  if (bbA.maxX < bbB.minX || bbA.minX > bbB.maxX || bbA.maxY < bbB.minY || bbA.minY > bbB.maxY) return false;
  for (const p of ptsA) if (pointInPolygon(p[0], p[1], ptsB)) return true;
  for (const p of ptsB) if (pointInPolygon(p[0], p[1], ptsA)) return true;
  for (let i=0; i<ptsA.length; i++) {
    for (let j=0; j<ptsB.length; j++) {
      if (segmentsIntersect(ptsA[i], ptsA[(i+1)%ptsA.length], ptsB[j], ptsB[(j+1)%ptsB.length])) return true;
    }
  }
  return false;
}

function shoelaceArea(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}

// ─────────────────────────────────────────────────────────────
// BOUNDARY PRESETS
// ─────────────────────────────────────────────────────────────
const BOUNDARY_DEFAULT_CX = 90, BOUNDARY_DEFAULT_CY = 65, BOUNDARY_DEFAULT_R = 55;
function genNGon(n, cx, cy, r) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    pts.push([snap(cx + r * Math.cos(a)), snap(cy + r * Math.sin(a))]);
  }
  return pts;
}

const BOUNDARY_PRESETS = {
  rectangle: [[15,15],[165,15],[165,110],[15,110]],
  l_shape:   [[15,15],[165,15],[165,62],[90,62],[90,110],[15,110]],
  pentagon:  genNGon(5, BOUNDARY_DEFAULT_CX, BOUNDARY_DEFAULT_CY, BOUNDARY_DEFAULT_R),
  hexagon:   genNGon(6, BOUNDARY_DEFAULT_CX, BOUNDARY_DEFAULT_CY, BOUNDARY_DEFAULT_R),
  trapezoid: [[51,15],[149,15],[165,110],[35,110]],
};

const BUILDING_SHAPES = {
  rectangle: { norm: [[0,0],[1,0],[1,1],[0,1]],            defW: 22, defH: 14, label: "Rectangle" },
  triangle:  { norm: [[0.5,0],[1,1],[0,1]],                 defW: 18, defH: 14, label: "Triangle"  },
  l_shape:   { norm: [[0,0],[1,0],[1,0.5],[0.5,0.5],[0.5,1],[0,1]], defW: 20, defH: 16, label: "L-Shape" },
  circle:    { norm: null,                                  defW: 14, defH: 14, label: "Circle"    },
};
const COLORS = ["#4A90D9", "#E07B39", "#6BBF59", "#9B59B6", "#16A085", "#D4AC0D", "#C0392B", "#7F8C8D"];

// ─────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────
let STATE = { boundary: null, buildings: [] };
let nextId = 1, selected = null, drag = null;
const svg = parentElement.querySelector("#canvas");

function scalePoints(norm, x, y, w, h) {
  return norm.map(([nx, ny]) => [x + nx * w, y + ny * h]);
}
function shapePoints(b) {
  let pts;
  if (b.shape === "circle") {
    const cx = b.x + b.w/2, cy = b.y + b.h/2, r = b.w/2;
    pts = [];
    for (let i = 0; i < 28; i++) {
      const a = (2 * Math.PI * i) / 28;
      pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    }
  } else {
    pts = scalePoints(BUILDING_SHAPES[b.shape].norm, b.x, b.y, b.w, b.h);
  }
  if (b.r) {
    const cx = b.x + b.w/2, cy = b.y + b.h/2;
    pts = pts.map(p => rotatePt(p, cx, cy, b.r));
  }
  return pts;
}

// ─────────────────────────────────────────────────────────────
// RENDER HELPERS
// ─────────────────────────────────────────────────────────────
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function pointsToAttr(pts) { return pts.map(p => p.join(",")).join(" "); }

function makeHandles(b) {
  const cx = b.x + b.w/2, cy = b.y + b.h/2;
  const group = el("g", {});
  if (b.r) group.setAttribute("transform", `rotate(${b.r}, ${cx}, ${cy})`);
  
  // corner resize handles
  const corners = [["nw", b.x, b.y], ["ne", b.x+b.w, b.y], ["sw", b.x, b.y+b.h], ["se", b.x+b.w, b.y+b.h]];
  for (const [corner, px, py] of corners) {
    if (b.shape === "circle" && corner !== "se") continue;
    group.appendChild(el("rect", {
      x: px - 2.6, y: py - 2.6, width: 5.2, height: 5.2,
      fill: "#fff", stroke: "#4A90D9", "stroke-width": 1,
      "data-role": "handle", "data-target": "resize", "data-id": b.id,
      style: `cursor:${corner}-resize`,
    }));
  }
  
  // rotation handle
  group.appendChild(el("line", { x1: cx, y1: b.y, x2: cx, y2: b.y - 14, stroke: "#4A90D9", "stroke-width": 1, "stroke-dasharray": "2,2" }));
  group.appendChild(el("circle", {
    cx: cx, cy: b.y - 14, r: 3.5,
    fill: "#4A90D9", stroke: "#fff", "stroke-width": 1,
    "data-role": "handle", "data-target": "rotate", "data-id": b.id,
    style: "cursor: crosshair",
  }));
  
  return group;
}

// ─────────────────────────────────────────────────────────────
// RENDER LOOP
// ─────────────────────────────────────────────────────────────
function render() {
  svg.innerHTML = "";

  const defs = el("defs", {});
  const pattern = el("pattern", { id: "grid", width: 10, height: 10, patternUnits: "userSpaceOnUse" });
  pattern.appendChild(el("path", { d: "M 10 0 L 0 0 0 10", fill: "none", stroke: "#EEF2F7", "stroke-width": 0.5 }));
  defs.appendChild(pattern);
  svg.appendChild(defs);
  svg.appendChild(el("rect", { x: 0, y: 0, width: WORLD_W, height: WORLD_H, fill: "url(#grid)" }));

  const bPts = STATE.boundary.points;
  const isBndSel = selected && selected.type === "boundary";
  svg.appendChild(el("polygon", {
    points: pointsToAttr(bPts), fill: "rgba(74,144,217,0.07)",
    stroke: isBndSel ? "#4A90D9" : "#9FB4CC", "stroke-width": isBndSel ? 2 : 1.3,
    "stroke-dasharray": "6,3", "data-role": "boundary",
  }));
  
  if (isBndSel) {
    const vg = el("g", {});
    bPts.forEach(([x, y], i) => {
      vg.appendChild(el("circle", {
        cx: x, cy: y, r: 3.5, fill: "#fff", stroke: "#4A90D9", "stroke-width": 1.4,
        "data-role": "handle", "data-target": "boundary-vertex", "data-index": i, style: "cursor:move",
      }));
    });
    svg.appendChild(vg);
  }

  STATE.buildings.forEach((b, idx) => {
    const pts = shapePoints(b);
    const inside = pts.every(p => pointInPolygon(p[0], p[1], bPts));
    const overlapping = STATE.buildings.some((o, j) => j !== idx && polysOverlap(pts, shapePoints(o)));
    const isSel = selected && selected.type === "building" && selected.id === b.id;

    const g = el("g", { "data-role": "building", "data-id": b.id, style: "cursor:move" });
    g.appendChild(el("polygon", {
      points: pointsToAttr(pts),
      fill: b.color, "fill-opacity": isSel ? 0.9 : 0.6,
      stroke: (!inside || overlapping) ? "#E74C3C" : b.color,
      "stroke-width": isSel ? 2.4 : 1.4,
      "stroke-dasharray": (!inside || overlapping) ? "4,2" : "none",
    }));

    const cx = b.x + b.w/2, cy = b.y + b.h/2;
    const label = el("text", {
      x: cx, y: cy, "text-anchor": "middle", "dominant-baseline": "middle",
      "font-size": 5.4, fill: "#1F2D3D", "pointer-events": "none",
    });
    if (b.r) label.setAttribute("transform", `rotate(${b.r}, ${cx}, ${cy})`);
    label.textContent = b.name;
    g.appendChild(label);

    if (!inside || overlapping) {
      const warn = el("text", { x: getBBox(pts).minX, y: getBBox(pts).minY - 1.5, "font-size": 6, "pointer-events": "none" });
      warn.textContent = "\u26A0";
      g.appendChild(warn);
    }
    
    svg.appendChild(g);
    if (isSel) svg.appendChild(makeHandles(b));
  });

  renderSidePanel();
}

function renderSidePanel() {
  const siteArea = shoelaceArea(STATE.boundary.points);
  const builtArea = STATE.buildings.reduce((s, b) => s + (b.shape==="circle"?Math.PI*(b.w/2)*(b.w/2):shoelaceArea(shapePoints(b))), 0);
  
  parentElement.querySelector("#statsRow").innerHTML = `
    <div class="stat">Site area<b>${siteArea.toFixed(0)} m&sup2;</b></div>
    <div class="stat">Built area<b>${builtArea.toFixed(0)} m&sup2;</b></div>
    <div class="stat">Utilisation<b>${siteArea>0?((builtArea/siteArea)*100).toFixed(1):0}%</b></div>
  `;

  const bldListEl = parentElement.querySelector("#bldList");
  bldListEl.innerHTML = "";
  if (STATE.buildings.length === 0) {
    bldListEl.innerHTML = '<div class="empty-list">No shapes yet.</div>';
    return;
  }
  
  STATE.buildings.forEach(b => {
    const row = document.createElement("div");
    row.className = "bld-row" + (selected && selected.type === "building" && selected.id === b.id ? " selected" : "");
    row.addEventListener("pointerdown", () => {
      // Bring to front on select
      STATE.buildings = STATE.buildings.filter(x => x.id !== b.id);
      STATE.buildings.push(b);
      selected = { type: "building", id: b.id };
      render();
    });

    const top = document.createElement("div");
    top.className = "top";
    
    const cp = document.createElement("input");
    cp.type = "color"; cp.className = "color-picker"; cp.value = b.color;
    cp.addEventListener("input", e => { b.color = e.target.value; render(); });
    cp.addEventListener("change", () => syncToPython());
    
    const ni = document.createElement("input");
    ni.type = "text"; ni.value = b.name;
    ni.addEventListener("input", e => b.name = e.target.value);
    ni.addEventListener("change", () => { render(); syncToPython(); });
    
    const dupBtn = document.createElement("button");
    dupBtn.className = "icon-btn"; dupBtn.title = "Duplicate"; dupBtn.innerHTML = "&#10697;";
    dupBtn.addEventListener("click", e => {
      e.stopPropagation();
      const copy = JSON.parse(JSON.stringify(b));
      copy.id = nextId++; copy.x += 5; copy.y += 5; copy.name += " (Copy)";
      STATE.buildings.push(copy);
      selected = { type: "building", id: copy.id };
      render(); syncToPython();
    });
    
    const delBtn = document.createElement("button");
    delBtn.className = "icon-btn del"; delBtn.title = "Delete"; delBtn.innerHTML = "&#10005;";
    delBtn.addEventListener("click", e => {
      e.stopPropagation();
      STATE.buildings = STATE.buildings.filter(x => x.id !== b.id);
      if (selected && selected.id === b.id) selected = null;
      render(); syncToPython();
    });
    
    top.appendChild(cp); top.appendChild(ni); top.appendChild(dupBtn); top.appendChild(delBtn);
    
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `${BUILDING_SHAPES[b.shape].label} &middot; ${b.r||0}&deg; rotation`;

    row.appendChild(top); row.appendChild(meta);
    bldListEl.appendChild(row);
  });
}

function syncToPython() {
  const siteArea = shoelaceArea(STATE.boundary.points);
  const builtArea = STATE.buildings.reduce((s, b) => s + (b.shape==="circle"?Math.PI*(b.w/2)*(b.w/2):shoelaceArea(shapePoints(b))), 0);
  setStateValue("layout", {
    boundary: STATE.boundary, buildings: STATE.buildings,
    site_area: siteArea, built_area: builtArea,
    utilization_pct: siteArea > 0 ? (builtArea / siteArea) * 100 : 0,
  });
}

// ─────────────────────────────────────────────────────────────
// TOOLBAR & INTERACTION
// ─────────────────────────────────────────────────────────────
parentElement.querySelector("#snapGrid").addEventListener("change", e => { SNAP = e.target.checked ? 5 : 1; });
parentElement.querySelector("#clearBtn").addEventListener("click", () => {
  if(confirm("Clear all shapes?")) { STATE.buildings = []; selected = null; render(); syncToPython(); }
});

function addBuilding(shape, worldX, worldY) {
  const def = BUILDING_SHAPES[shape];
  const x = worldX !== undefined ? snap(worldX - def.defW/2) : snap(20 + (STATE.buildings.length % 5)*4);
  const y = worldY !== undefined ? snap(worldY - def.defH/2) : snap(20 + (STATE.buildings.length % 5)*4);
  const b = {
    id: nextId++, shape, x, y, w: def.defW, h: def.defH, r: 0,
    name: `${def.label} ${STATE.buildings.length + 1}`,
    color: COLORS[STATE.buildings.length % COLORS.length],
  };
  STATE.buildings.push(b);
  selected = { type: "building", id: b.id };
  render(); syncToPython();
}

parentElement.querySelectorAll(".shape-btn[data-shape]").forEach(btn => {
  btn.addEventListener("click", () => addBuilding(btn.dataset.shape));
  btn.addEventListener("dragstart", e => { e.dataTransfer.setData("text", btn.dataset.shape); });
});
svg.addEventListener("dragover", e => e.preventDefault());
svg.addEventListener("drop", e => {
  e.preventDefault();
  const shape = e.dataTransfer.getData("text");
  if (!BUILDING_SHAPES[shape]) return;
  const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  addBuilding(shape, p.x, p.y);
});

const bSel = parentElement.querySelector("#boundarySelect");
const bSides = parentElement.querySelector("#boundarySides");
bSel.addEventListener("change", () => {
  const p = bSel.value;
  STATE.boundary = { preset: p, sides: BOUNDARY_PRESETS[p].length, points: BOUNDARY_PRESETS[p].map(x => [...x]) };
  bSides.value = STATE.boundary.sides;
  render(); syncToPython();
});
bSides.addEventListener("change", () => {
  let n = clamp(Math.round(Number(bSides.value))||4, 3, 20);
  bSides.value = n;
  let sx=0, sy=0; STATE.boundary.points.forEach(p => { sx+=p[0]; sy+=p[1]; });
  STATE.boundary = { preset: "custom", sides: n, points: genNGon(n, sx/STATE.boundary.points.length, sy/STATE.boundary.points.length, BOUNDARY_DEFAULT_R) };
  render(); syncToPython();
});

// POINTER EVENTS
svg.addEventListener("pointerdown", e => {
  const target = e.target.closest("[data-role]");
  const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());

  if (!target) { selected = null; render(); return; }
  const role = target.getAttribute("data-role");

  if (role === "handle") {
    const tType = target.getAttribute("data-target");
    if (tType === "boundary-vertex") {
      selected = { type: "boundary" };
      drag = { mode: "vertex", index: Number(target.getAttribute("data-index")) };
    } else {
      const obj = STATE.buildings.find(b => String(b.id) === target.getAttribute("data-id"));
      if (!obj) return;
      if (tType === "rotate") {
        drag = { mode: "rotate", obj };
      } else {
        // For accurate symmetric resize, grab the CTM of the rotated handle group
        drag = { mode: "resize", obj, isCircle: obj.shape==="circle", ctm: target.closest('g').getScreenCTM().inverse() };
      }
    }
    svg.setPointerCapture(e.pointerId);
    return;
  }
  
  if (role === "building") {
    const id = Number(target.getAttribute("data-id"));
    const b = STATE.buildings.find(x => x.id === id);
    if (!b) return;
    STATE.buildings = STATE.buildings.filter(x => x.id !== id);
    STATE.buildings.push(b);
    selected = { type: "building", id };
    drag = { mode: "move", obj: b, offX: p.x - b.x, offY: p.y - b.y };
    svg.setPointerCapture(e.pointerId);
    render(); return;
  }
  
  if (role === "boundary") { selected = { type: "boundary" }; render(); }
});

svg.addEventListener("pointermove", e => {
  if (!drag) return;
  const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  const wx = p.x, wy = p.y, obj = drag.obj;

  if (drag.mode === "vertex") {
    STATE.boundary.points[drag.index] = [clamp(snap(wx), -WORLD_W, WORLD_W*2), clamp(snap(wy), -WORLD_H, WORLD_H*2)];
  } else if (drag.mode === "move") {
    obj.x = clamp(snap(wx - drag.offX), -WORLD_W, WORLD_W*2);
    obj.y = clamp(snap(wy - drag.offY), -WORLD_H, WORLD_H*2);
  } else if (drag.mode === "rotate") {
    const cx = obj.x + obj.w/2, cy = obj.y + obj.h/2;
    let deg = (Math.atan2(wy - cy, wx - cx) * 180 / Math.PI) + 90;
    if (e.shiftKey) deg = Math.round(deg/15)*15; // Shift to snap 15 deg
    else deg = Math.round(deg/5)*5; // Standard 5 deg snap
    obj.r = (deg % 360 + 360) % 360;
  } else if (drag.mode === "resize") {
    // Symmetrical resize using the local coordinate matrix
    const localP = pt.matrixTransform(drag.ctm);
    const cx = obj.x + obj.w/2, cy = obj.y + obj.h/2;
    if (drag.isCircle) {
      const r = Math.max(MIN_SIZE/2, Math.hypot(localP.x - cx, localP.y - cy));
      obj.w = obj.h = snap(r * 2);
    } else {
      obj.w = snap(Math.max(MIN_SIZE, Math.abs(localP.x - cx) * 2));
      obj.h = snap(Math.max(MIN_SIZE, Math.abs(localP.y - cy) * 2));
    }
    obj.x = cx - obj.w/2; obj.y = cy - obj.h/2;
  }
  render();
});

function endDrag(e) {
  if (!drag) return;
  drag = null;
  try { svg.releasePointerCapture(e.pointerId); } catch(e){}
  syncToPython();
}
svg.addEventListener("pointerup", endDrag);
svg.addEventListener("pointercancel", endDrag);

// ─────────────────────────────────────────────────────────────
// INITIALIZATION
// ─────────────────────────────────────────────────────────────
function loadState(raw) {
  let s = raw ? JSON.parse(JSON.stringify(raw)) : {};
  if (!s.boundary) s.boundary = { preset: "rectangle", sides: 4, points: BOUNDARY_PRESETS.rectangle.map(p => [...p]) };
  if (!s.buildings) s.buildings = [];
  STATE = s;
  nextId = STATE.buildings.reduce((m, b) => Math.max(m, b.id + 1), 1);
  selected = null;
}

loadState(data);
bSel.value = STATE.boundary.preset;
bSides.value = STATE.boundary.sides;
render();
if (!data || data.site_area === undefined) syncToPython();
}
"""

_site_canvas = st.components.v2.component(
    "site_canvas",
    html=_CANVAS_HTML,
    css=_CANVAS_CSS,
    js=_CANVAS_JS,
)

def site_canvas(initial_state: dict, version: int):
    return _site_canvas(
        data=initial_state,
        default={"layout": initial_state},
        key=f"canvas-{version}",
        height=620,
        on_layout_change=lambda: None,
    )

# ─────────────────────────────────────────────────────────────
# DEFAULT STATE & PYTHON LAYOUT
# ─────────────────────────────────────────────────────────────
DEFAULT_STATE = {
    "boundary": {
        "preset": "rectangle",
        "sides": 4,
        "points": [[15, 15], [165, 15], [165, 110], [15, 110]],
    },
    "buildings": [],
    "site_area": 14250,
    "built_area": 0,
    "utilization_pct": 0.0,
}

if "site_state" not in st.session_state:
    st.session_state.site_state = copy.deepcopy(DEFAULT_STATE)
if "version" not in st.session_state:
    st.session_state.version = 1
if "_last_upload_id" not in st.session_state:
    st.session_state._last_upload_id = None

with st.sidebar:
    st.markdown("### 🏗️ Site Planner")
    st.caption("Drag shapes to build your layout.")
    st.divider()

    uploaded = st.file_uploader("📂 Load layout (JSON)", type="json")
    if uploaded is not None:
        upload_id = (uploaded.name, uploaded.size)
        if upload_id != st.session_state._last_upload_id:
            try:
                loaded = json.loads(uploaded.read())
                if "boundary" in loaded and "buildings" in loaded:
                    st.session_state.site_state = loaded
                    st.session_state.version += 1
                    st.session_state._last_upload_id = upload_id
            except Exception:
                pass

    if st.button("🔄 Reset layout", use_container_width=True):
        st.session_state.site_state = copy.deepcopy(DEFAULT_STATE)
        st.session_state.version += 1
        st.session_state._last_upload_id = None

st.markdown("## 🏗️ Construction Site Planner")

result = site_canvas(
    initial_state=st.session_state.site_state,
    version=st.session_state.version,
)
if result is not None and result.get("layout") is not None:
    st.session_state.site_state = result["layout"]

with st.sidebar:
    st.divider()
    st.download_button(
        "
