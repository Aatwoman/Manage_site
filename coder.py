"""
Construction Site Planner  ·  v5.0 (single-file, Custom Components v2)
─────────────────────────────────────────────────────────────────────────────
Everything — Python, HTML, CSS, and JS — lives in this one file. No separate
components/canvas/index.html, no folder structure to get right when
deploying: just this file plus requirements.txt at the root of your repo.

This uses Streamlit's Custom Components v2 API (st.components.v2.component,
added in Streamlit 1.51), which accepts raw HTML/CSS/JS as Python strings
directly — no declare_component(path=...) pointing at a file on disk, and no
hand-rolled postMessage protocol. Communication with Python is native to the
API: the JS side calls setStateValue("layout", {...}) whenever an edit
commits (a drag ends, a dropdown changes, etc.), and Python reads it back via
result.layout after the component call. This is the same officially
supported, reliable approach as before — just inlined instead of split
across files.

One v2-specific design note: a v2 component receives its `data` only once,
at mount time. Updating `data` on a later Streamlit rerun does not push new
values into an already-mounted instance — to force a fresh load (e.g. after
"Reset" or after uploading a saved JSON layout), this app bumps a `version`
counter and folds it into the component's `key`, which forces v2 to remount
the component with the new data. Ongoing edits within a single mount
(dragging, typing) flow back to Python via setStateValue/result.layout as
normal and don't need a remount.
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
      <label>Add building (drag onto site):</label>
      <button class="shape-btn" draggable="true" data-shape="rectangle"><span class="shape-icon">&#9646;</span>Rectangle</button>
      <button class="shape-btn" draggable="true" data-shape="circle"><span class="shape-icon">&#9679;</span>Circle</button>
      <button class="shape-btn" draggable="true" data-shape="triangle"><span class="shape-icon">&#9650;</span>Triangle</button>
      <button class="shape-btn" draggable="true" data-shape="l_shape"><span class="shape-icon">&#8990;</span>L-Shape</button>
    </div>
    <div class="group">
      <label>Site boundary:</label>
      <select id="boundarySelect">
        <option value="rectangle">Rectangle</option>
        <option value="l_shape">L-Shape</option>
        <option value="pentagon">Pentagon</option>
        <option value="hexagon">Hexagon</option>
        <option value="trapezoid">Trapezoid</option>
      </select>
    </div>
    <div class="group">
      <label>Sides:</label>
      <input type="number" id="boundarySides" min="3" max="20" step="1" style="width:54px" />
    </div>
  </div>
  <div class="hint">Drag a shape onto the site to add it (or click it). Drag a building to move it; drag a corner square to resize it. Click the boundary to select it, then drag any vertex (small circle) to reshape it — change "Sides" to regenerate it with a different number of vertices. Click empty space to deselect.</div>

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

  #toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 8px; }
  .group { display: flex; align-items: center; gap: 6px; }
  .group label { font-size: 12px; font-weight: 600; color: #4A5A6A; }

  .shape-btn {
    display: flex; align-items: center; gap: 5px;
    border: 1px solid #C7D4E2; background: #fff; border-radius: 8px;
    padding: 6px 10px; font-size: 12.5px; cursor: grab; user-select: none;
    transition: box-shadow .15s, transform .15s;
  }
  .shape-btn:hover { box-shadow: 0 2px 6px rgba(0,0,0,.12); transform: translateY(-1px); }
  .shape-btn:active { cursor: grabbing; }
  .shape-icon { font-size: 14px; }

  select, input[type="text"], input[type="number"] {
    border: 1px solid #C7D4E2; border-radius: 6px; padding: 4px 7px; font-size: 12.5px;
  }

  .hint { font-size: 11.5px; color: #8094A8; margin-bottom: 8px; }

  #main { display: flex; gap: 12px; align-items: flex-start; }

  #canvasWrap {
    flex: 1 1 auto; border: 1px solid #D4DFEA; border-radius: 10px; background: #fff;
    min-width: 0; position: relative;
  }
  svg#canvas { width: 100%; height: auto; display: block; border-radius: 10px; touch-action: none; }

  #side {
    flex: 0 0 240px; max-width: 240px;
    border: 1px solid #D4DFEA; border-radius: 10px; background: #fff; padding: 10px;
    max-height: 480px; overflow-y: auto;
  }
  #side h4 { margin: 0 0 8px; font-size: 12.5px; color: #4A5A6A; }

  .stats-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
  .stat {
    background: #F0F4FA; border-left: 3px solid #4A90D9; border-radius: 6px;
    padding: 5px 8px; font-size: 11px; flex: 1 1 70px;
  }
  .stat b { display: block; font-size: 13.5px; }

  .bld-row {
    border: 1px solid #E3EAF2; border-radius: 8px; padding: 7px 8px; margin-bottom: 7px;
  }
  .bld-row.selected { border-color: #4A90D9; background: #F3F8FE; }
  .bld-row .top { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
  .swatch { width: 10px; height: 10px; border-radius: 3px; flex: none; }
  .bld-row input[type="text"] { flex: 1 1 auto; min-width: 0; font-size: 12px; }
  .bld-row .meta { font-size: 10.5px; color: #8094A8; margin-bottom: 5px; }
  .bld-row .thresh-row { display: flex; align-items: center; gap: 5px; }
  .bld-row .thresh-row label { font-size: 11px; color: #4A5A6A; }
  .bld-row .thresh-row input { width: 70px; }
  .del-btn {
    border: none; background: #FCEAEA; color: #C0392B; border-radius: 6px;
    width: 20px; height: 20px; cursor: pointer; font-size: 12px; flex: none; line-height: 1;
  }
  .empty-list { font-size: 12px; color: #95A5B5; text-align: center; padding: 14px 4px; }

  .warn-badge { color: #E74C3C; font-size: 10.5px; font-weight: 600; }
"""

_CANVAS_JS = """
export default function(component) {
const { data, parentElement, setStateValue } = component;

// ─────────────────────────────────────────────────────────────
// CONSTANTS / GEOMETRY DEFINITIONS
// ─────────────────────────────────────────────────────────────
const WORLD_W = 200, WORLD_H = 130;
const MIN_SIZE = 3;
const SNAP = 0.5;

function snap(v) { return Math.round(v / SNAP) * SNAP; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// Boundary presets are ABSOLUTE world-coordinate point lists (not
// normalized 0-1 + a box) since vertices are dragged independently and
// there's no longer a single box that the whole shape scales against.
// These are just *starting points* for the dropdown / sides-input reset —
// every point is freely draggable afterward.
const BOUNDARY_DEFAULT_CX = 90, BOUNDARY_DEFAULT_CY = 65;   // roughly centered in WORLD_W x WORLD_H
const BOUNDARY_DEFAULT_R = 55;

function genNGon(n, cx, cy, r) {
  // Evenly spaced N-sided polygon, point 0 at the top, going clockwise —
  // used both for named presets that happen to be regular polygons and
  // for the freeform "sides: N" regenerate.
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
// STATE  (seeded once from `data`, the Python-side layout passed in
// at mount time — see loadState() below, which also migrates any
// old-format save file the user might load)
// ─────────────────────────────────────────────────────────────
let STATE = { boundary: { preset: "rectangle", sides: 4, points: BOUNDARY_PRESETS.rectangle.map(p => [...p]) }, buildings: [] };
let nextId = 1;
let selected = null;        // { type: 'building', id } | { type: 'boundary' } | null
let drag = null;            // active pointer drag info

const svg = parentElement.querySelector("#canvas");
const bldListEl = parentElement.querySelector("#bldList");
const statsRowEl = parentElement.querySelector("#statsRow");
const boundarySelect = parentElement.querySelector("#boundarySelect");
const boundarySidesInput = parentElement.querySelector("#boundarySides");

// ─────────────────────────────────────────────────────────────
// GEOMETRY HELPERS
// ─────────────────────────────────────────────────────────────
function scalePoints(norm, x, y, w, h) {
  return norm.map(([nx, ny]) => [x + nx * w, y + ny * h]);
}
function shapePoints(b) {
  if (b.shape === "circle") {
    const cx = b.x + b.w / 2, cy = b.y + b.h / 2, r = b.w / 2;
    const n = 28, pts = [];
    for (let i = 0; i < n; i++) {
      const a = (2 * Math.PI * i) / n;
      pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
    }
    return pts;
  }
  return scalePoints(BUILDING_SHAPES[b.shape].norm, b.x, b.y, b.w, b.h);
}
function boundaryPoints(bnd) {
  return bnd.points;
}
function polygonCentroid(pts) {
  // Simple averaged centroid (not the area-weighted centroid) — good enough
  // for "keep the shape roughly where it was" when regenerating vertex count.
  let sx = 0, sy = 0;
  for (const [x, y] of pts) { sx += x; sy += y; }
  return [sx / pts.length, sy / pts.length];
}
function shoelaceArea(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}
function pointInPolygon(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function rectsOverlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function screenToWorld(clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX; pt.y = clientY;
  const ctm = svg.getScreenCTM().inverse();
  const p = pt.matrixTransform(ctm);
  return [p.x, p.y];
}

function buildingInsideBoundary(b) {
  const bp = boundaryPoints(STATE.boundary);
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  return pointInPolygon(cx, cy, bp);
}

function buildingArea(b) {
  if (b.shape === "circle") return Math.PI * (b.w / 2) * (b.w / 2);
  return shoelaceArea(shapePoints(b));
}

// ─────────────────────────────────────────────────────────────
// SVG ELEMENT HELPERS
// ─────────────────────────────────────────────────────────────
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function pointsToAttr(pts) { return pts.map(p => p.join(",")).join(" "); }

function makeHandles(bbox, role, id) {
  const [x0, y0, x1, y1] = bbox;
  const corners = [["nw", x0, y0], ["ne", x1, y0], ["sw", x0, y1], ["se", x1, y1]];
  const group = el("g", {});
  for (const [corner, cx, cy] of corners) {
    const h = el("rect", {
      x: cx - 2.6, y: cy - 2.6, width: 5.2, height: 5.2,
      fill: "#fff", stroke: "#4A90D9", "stroke-width": 1,
      "data-role": "handle", "data-target": role, "data-id": id || "", "data-corner": corner,
      style: `cursor:${corner}-resize`,
    });
    group.appendChild(h);
  }
  return group;
}

function makeVertexHandles(pts) {
  // One draggable circular handle per boundary vertex — round, rather than
  // the square corner-resize handles, so the two interaction styles read
  // as visually distinct at a glance.
  const group = el("g", {});
  pts.forEach(([x, y], i) => {
    const h = el("circle", {
      cx: x, cy: y, r: 3,
      fill: "#fff", stroke: "#4A90D9", "stroke-width": 1.4,
      "data-role": "handle", "data-target": "boundary-vertex", "data-index": i,
      style: "cursor:move",
    });
    group.appendChild(h);
  });
  return group;
}

// ─────────────────────────────────────────────────────────────
// RENDER
// ─────────────────────────────────────────────────────────────
function render() {
  svg.innerHTML = "";

  // grid background
  const defs = el("defs", {});
  const pattern = el("pattern", { id: "grid", width: 10, height: 10, patternUnits: "userSpaceOnUse" });
  pattern.appendChild(el("path", { d: "M 10 0 L 0 0 0 10", fill: "none", stroke: "#EEF2F7", "stroke-width": 0.4 }));
  defs.appendChild(pattern);
  svg.appendChild(defs);
  svg.appendChild(el("rect", { x: 0, y: 0, width: WORLD_W, height: WORLD_H, fill: "url(#grid)" }));

  // boundary — selecting it shows one draggable handle per vertex; there's
  // no separate "move the whole shape" mode, only per-vertex editing.
  const bPts = boundaryPoints(STATE.boundary);
  const isBndSel = selected && selected.type === "boundary";
  svg.appendChild(el("polygon", {
    points: pointsToAttr(bPts), fill: "rgba(74,144,217,0.07)",
    stroke: isBndSel ? "#4A90D9" : "#9FB4CC", "stroke-width": isBndSel ? 2 : 1.3,
    "stroke-dasharray": "6,3", "data-role": "boundary",
  }));
  if (isBndSel) {
    svg.appendChild(makeVertexHandles(bPts));
  }

  // buildings
  STATE.buildings.forEach((b, idx) => {
    const pts = shapePoints(b);
    const inside = buildingInsideBoundary(b);
    const overlapping = STATE.buildings.some((o, j) => j !== idx && rectsOverlap(b, o));
    const isSel = selected && selected.type === "building" && selected.id === b.id;

    const g = el("g", { "data-role": "building", "data-id": b.id, style: "cursor:move" });
    const poly = el("polygon", {
      points: pointsToAttr(pts),
      fill: b.color, "fill-opacity": isSel ? 0.85 : 0.6,
      stroke: (!inside || overlapping) ? "#E74C3C" : b.color,
      "stroke-width": isSel ? 2.4 : 1.4,
      "stroke-dasharray": (!inside || overlapping) ? "4,2" : "none",
    });
    g.appendChild(poly);

    const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
    const label = el("text", {
      x: cx, y: cy, "text-anchor": "middle", "dominant-baseline": "middle",
      "font-size": 5.4, fill: "#1F2D3D", "pointer-events": "none",
    });
    label.textContent = b.name;
    g.appendChild(label);

    if (!inside || overlapping) {
      const warn = el("text", { x: b.x, y: b.y - 1.5, "font-size": 6, "pointer-events": "none" });
      warn.textContent = "\u26A0";
      g.appendChild(warn);
    }

    svg.appendChild(g);
    if (isSel) {
      const bb = [b.x, b.y, b.x + b.w, b.y + b.h];
      const handleGroup = makeHandles(bb, "building", b.id);
      if (b.shape === "circle") {
        // only the se handle is meaningful for circles (uniform radius)
        [...handleGroup.children].forEach(h => {
          if (h.getAttribute("data-corner") !== "se") h.style.display = "none";
        });
      }
      svg.appendChild(handleGroup);
    }
  });

  renderSidePanel();
}

function renderSidePanel() {
  // stats
  const siteArea = shoelaceArea(boundaryPoints(STATE.boundary));
  const builtArea = STATE.buildings.reduce((s, b) => s + buildingArea(b), 0);
  const pct = siteArea > 0 ? (builtArea / siteArea) * 100 : 0;
  statsRowEl.innerHTML = `
    <div class="stat">Site area<b>${siteArea.toFixed(0)} m&sup2;</b></div>
    <div class="stat">Built area<b>${builtArea.toFixed(0)} m&sup2;</b></div>
    <div class="stat">Utilisation<b>${pct.toFixed(1)}%</b></div>
  `;

  // building list
  bldListEl.innerHTML = "";
  if (STATE.buildings.length === 0) {
    bldListEl.innerHTML = '<div class="empty-list">No buildings yet —<br/>drag a shape onto the site.</div>';
    return;
  }
  STATE.buildings.forEach(b => {
    const inside = buildingInsideBoundary(b);
    const row = document.createElement("div");
    row.className = "bld-row" + (selected && selected.type === "building" && selected.id === b.id ? " selected" : "");
    row.addEventListener("pointerdown", () => { selected = { type: "building", id: b.id }; render(); });

    const top = document.createElement("div");
    top.className = "top";
    const sw = document.createElement("div");
    sw.className = "swatch"; sw.style.background = b.color;
    const nameInput = document.createElement("input");
    nameInput.type = "text"; nameInput.value = b.name;
    nameInput.addEventListener("input", e => { b.name = e.target.value; });
    nameInput.addEventListener("change", () => { render(); syncToPython(); });
    const delBtn = document.createElement("button");
    delBtn.className = "del-btn"; delBtn.textContent = "\u2715";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      STATE.buildings = STATE.buildings.filter(x => x.id !== b.id);
      if (selected && selected.type === "building" && selected.id === b.id) selected = null;
      render(); syncToPython();
    });
    top.appendChild(sw); top.appendChild(nameInput); top.appendChild(delBtn);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `${BUILDING_SHAPES[b.shape].label} &middot; ${buildingArea(b).toFixed(1)} m&sup2;` +
      (inside ? "" : ' &middot; <span class="warn-badge">outside boundary</span>');

    const threshRow = document.createElement("div");
    threshRow.className = "thresh-row";
    const tLabel = document.createElement("label");
    tLabel.textContent = "Threshold:";
    const tInput = document.createElement("input");
    tInput.type = "number"; tInput.step = "any"; tInput.value = b.threshold;
    tInput.addEventListener("input", e => { b.threshold = e.target.value; });
    tInput.addEventListener("change", () => { syncToPython(); });
    threshRow.appendChild(tLabel); threshRow.appendChild(tInput);

    row.appendChild(top); row.appendChild(meta); row.appendChild(threshRow);
    bldListEl.appendChild(row);
  });
}

// ─────────────────────────────────────────────────────────────
// SYNC TO PYTHON  (only on discrete events — never mid-drag)
// ─────────────────────────────────────────────────────────────
function syncToPython() {
  const siteArea = shoelaceArea(boundaryPoints(STATE.boundary));
  const builtArea = STATE.buildings.reduce((s, b) => s + buildingArea(b), 0);
  setStateValue("layout", {
    boundary: STATE.boundary,
    buildings: STATE.buildings,
    site_area: siteArea,
    built_area: builtArea,
    utilization_pct: siteArea > 0 ? (builtArea / siteArea) * 100 : 0,
  });
}

// ─────────────────────────────────────────────────────────────
// ADD BUILDING
// ─────────────────────────────────────────────────────────────
function addBuilding(shape, worldX, worldY) {
  const def = BUILDING_SHAPES[shape];
  const w = def.defW, h = def.defH;
  const x = worldX !== undefined ? snap(worldX - w / 2) : snap(20 + (STATE.buildings.length % 5) * 4);
  const y = worldY !== undefined ? snap(worldY - h / 2) : snap(20 + (STATE.buildings.length % 5) * 4);
  const b = {
    id: nextId++,
    shape, x: clamp(x, 0, WORLD_W - w), y: clamp(y, 0, WORLD_H - h), w, h,
    name: `${def.label} ${STATE.buildings.length + 1}`,
    threshold: 0,
    color: COLORS[STATE.buildings.length % COLORS.length],
  };
  STATE.buildings.push(b);
  selected = { type: "building", id: b.id };
  render();
  syncToPython();
}

// palette: click-to-add
parentElement.querySelectorAll(".shape-btn").forEach(btn => {
  btn.addEventListener("click", () => addBuilding(btn.dataset.shape));
  btn.addEventListener("dragstart", e => {
    e.dataTransfer.setData("text/plain", btn.dataset.shape);
    e.dataTransfer.effectAllowed = "copy";
  });
});
svg.addEventListener("dragover", e => { e.preventDefault(); });
svg.addEventListener("drop", e => {
  e.preventDefault();
  const shape = e.dataTransfer.getData("text/plain");
  if (!BUILDING_SHAPES[shape]) return;
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);
  addBuilding(shape, wx, wy);
});

// boundary preset selector
boundarySelect.addEventListener("change", () => {
  const preset = boundarySelect.value;
  const shape = BOUNDARY_PRESETS[preset];
  STATE.boundary = { preset, sides: shape.length, points: shape.map(p => [...p]) };
  boundarySidesInput.value = shape.length;
  render();
  syncToPython();
});

boundarySidesInput.addEventListener("change", () => {
  let n = Math.round(Number(boundarySidesInput.value));
  if (!Number.isFinite(n)) n = STATE.boundary.points.length;
  n = clamp(n, 3, 20);
  boundarySidesInput.value = n;

  // Regenerate around the boundary's current centroid (and a radius derived
  // from its current extent) so changing the side count doesn't relocate or
  // wildly resize a shape the user already dragged into place.
  const [cx, cy] = polygonCentroid(STATE.boundary.points);
  const xs = STATE.boundary.points.map(p => p[0]), ys = STATE.boundary.points.map(p => p[1]);
  const r = Math.max(10, (Math.max(...xs) - Math.min(...xs) + Math.max(...ys) - Math.min(...ys)) / 4);

  STATE.boundary = { preset: "custom", sides: n, points: genNGon(n, cx, cy, r) };
  render();
  syncToPython();
});

// ─────────────────────────────────────────────────────────────
// POINTER INTERACTION (move + resize), via native hit-testing
// ─────────────────────────────────────────────────────────────
svg.addEventListener("pointerdown", e => {
  const target = e.target.closest("[data-role]");
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);

  if (!target) { selected = null; render(); return; }
  const role = target.getAttribute("data-role");

  if (role === "handle") {
    const targetType = target.getAttribute("data-target");

    if (targetType === "boundary-vertex") {
      const index = Number(target.getAttribute("data-index"));
      selected = { type: "boundary" };
      drag = { mode: "vertex", index };
      svg.setPointerCapture(e.pointerId);
      return;
    }

    const corner = target.getAttribute("data-corner");
    const id = target.getAttribute("data-id");
    const obj = STATE.buildings.find(b => String(b.id) === id);
    if (!obj) return;
    drag = { mode: "resize", obj, corner, isCircle: obj.shape === "circle" };
    svg.setPointerCapture(e.pointerId);
    return;
  }

  if (role === "building") {
    const id = Number(target.getAttribute("data-id"));
    const b = STATE.buildings.find(x => x.id === id);
    if (!b) return;
    selected = { type: "building", id };
    drag = { mode: "move", obj: b, offX: wx - b.x, offY: wy - b.y };
    svg.setPointerCapture(e.pointerId);
    render();
    return;
  }

  if (role === "boundary") {
    // Clicking the boundary fill selects it (shows vertex handles) but, per
    // design, doesn't drag the whole shape — only individual vertices move.
    selected = { type: "boundary" };
    render();
    return;
  }
});

svg.addEventListener("pointermove", e => {
  if (!drag) return;
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);
  const obj = drag.obj;

  if (drag.mode === "vertex") {
    const nx = clamp(snap(wx), -WORLD_W * 0.3, WORLD_W * 1.3);
    const ny = clamp(snap(wy), -WORLD_H * 0.3, WORLD_H * 1.3);
    STATE.boundary.points[drag.index] = [nx, ny];
    render();
  } else if (drag.mode === "move") {
    obj.x = clamp(snap(wx - drag.offX), -WORLD_W * 0.3, WORLD_W * 1.3);
    obj.y = clamp(snap(wy - drag.offY), -WORLD_H * 0.3, WORLD_H * 1.3);
    render();
  } else if (drag.mode === "resize") {
    if (drag.isCircle) {
      const cx = obj.x + obj.w / 2, cy = obj.y + obj.h / 2;
      const r = Math.max(MIN_SIZE / 2, Math.hypot(wx - cx, wy - cy));
      obj.w = obj.h = snap(r * 2);
      obj.x = cx - obj.w / 2; obj.y = cy - obj.h / 2;
    } else {
      let x0 = obj.x, y0 = obj.y, x1 = obj.x + obj.w, y1 = obj.y + obj.h;
      const c = drag.corner;
      if (c.includes("w")) x0 = Math.min(snap(wx), x1 - MIN_SIZE);
      if (c.includes("e")) x1 = Math.max(snap(wx), x0 + MIN_SIZE);
      if (c.includes("n")) y0 = Math.min(snap(wy), y1 - MIN_SIZE);
      if (c.includes("s")) y1 = Math.max(snap(wy), y0 + MIN_SIZE);
      obj.x = x0; obj.y = y0; obj.w = x1 - x0; obj.h = y1 - y0;
    }
    render();
  }
});

function endDrag(e) {
  if (!drag) return;
  drag = null;
  try { svg.releasePointerCapture(e.pointerId); } catch (err) {}
  syncToPython();
}
svg.addEventListener("pointerup", endDrag);
svg.addEventListener("pointercancel", endDrag);

// ─────────────────────────────────────────────────────────────
// LOAD INITIAL STATE  (from `data`, passed in once at mount time;
// reloads/resets from Python work by remounting with a new `key`,
// not by pushing updates into an already-mounted instance — see
// app.py, which bumps a version counter into the component key)
// ─────────────────────────────────────────────────────────────
function loadState(raw) {
  let s = raw ? JSON.parse(JSON.stringify(raw)) : null;

  if (!s || !s.boundary) {
    s = s || {};
    s.boundary = { preset: "rectangle", sides: 4, points: BOUNDARY_PRESETS.rectangle.map(p => [...p]) };
  } else if (!Array.isArray(s.boundary.points)) {
    // Migrate a save file from the previous version of this app, which
    // stored { preset, x, y, w, h } and re-derived points from a fixed
    // normalized shape at render time. Re-derive them once here instead.
    const preset = s.boundary.preset && BOUNDARY_PRESETS[s.boundary.preset]
      ? s.boundary.preset : "rectangle";
    const { x = 15, y = 15, w = 150, h = 95 } = s.boundary;
    const OLD_NORM = {
      rectangle: [[0,0],[1,0],[1,1],[0,1]],
      l_shape:   [[0,0],[1,0],[1,0.5],[0.5,0.5],[0.5,1],[0,1]],
      pentagon:  [[0.5,0],[1,0.38],[0.81,1],[0.19,1],[0,0.38]],
      hexagon:   [[0.25,0],[0.75,0],[1,0.5],[0.75,1],[0.25,1],[0,0.5]],
      trapezoid: [[0.18,0],[0.82,0],[1,1],[0,1]],
    };
    const pts = OLD_NORM[preset].map(([nx, ny]) => [snap(x + nx * w), snap(y + ny * h)]);
    s.boundary = { preset, sides: pts.length, points: pts };
  }
  if (!s.boundary.sides) s.boundary.sides = s.boundary.points.length;
  if (!s.buildings) s.buildings = [];

  STATE = s;
  nextId = STATE.buildings.reduce((m, b) => Math.max(m, b.id + 1), 1);
  selected = null;
}

loadState(data);
boundarySelect.value = STATE.boundary.preset;
boundarySidesInput.value = STATE.boundary.sides;
render();

// Echo the freshly-loaded state straight back to Python only if it doesn't
// already contain the calculated metrics. This prevents an infinite rerun loop.
if (!data || data.site_area === undefined) {
  syncToPython();
}

}
"""

_site_canvas = st.components.v2.component(
    "site_canvas",
    html=_CANVAS_HTML,
    css=_CANVAS_CSS,
    js=_CANVAS_JS,
)


def site_canvas(initial_state: dict, version: int):
    # `key` includes `version` so that bumping version (on reset/load) forces
    # Streamlit to remount the component with the freshly-passed `data`,
    # rather than reusing an already-mounted instance that already consumed
    # its initial data at first mount.
    return _site_canvas(
        data=initial_state,
        default={"layout": initial_state},
        key=f"canvas-{version}",
        height=620,
        on_layout_change=lambda: None,
    )


# ─────────────────────────────────────────────────────────────
# DEFAULT STATE
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


def _init_state():
    if "site_state" not in st.session_state:
        st.session_state.site_state = copy.deepcopy(DEFAULT_STATE)
    if "version" not in st.session_state:
        st.session_state.version = 1
    if "_last_upload_id" not in st.session_state:
        st.session_state._last_upload_id = None


_init_state()

# ─────────────────────────────────────────────────────────────
# SIDEBAR (part 1): load / reset — these must run *before* the canvas
# call below, so a version bump takes effect in the same click.
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏗️ Site Planner")
    st.caption("Drag shapes onto the canvas to build your layout.")
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
                else:
                    st.error("That JSON doesn't look like a site layout.")
            except Exception as e:
                st.error(f"Couldn't read that file: {e}")

    if st.button("🔄 Reset layout", use_container_width=True):
        st.session_state.site_state = copy.deepcopy(DEFAULT_STATE)
        st.session_state.version += 1
        st.session_state._last_upload_id = None

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
st.markdown("## 🏗️ Construction Site Planner")

result = site_canvas(
    initial_state=st.session_state.site_state,
    version=st.session_state.version,
)
if result is not None and result.get("layout") is not None:
    st.session_state.site_state = result["layout"]

# ─────────────────────────────────────────────────────────────
# SIDEBAR (part 2): download — placed *after* the canvas call above
# so it always packages the freshest state, never a stale one.
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.download_button(
        "💾 Download layout (JSON)",
        data=json.dumps(st.session_state.site_state, indent=2),
        file_name="site_layout.json",
        mime="application/json",
        use_container_width=True,
    )

# ── Summary metrics (derived straight from what the component sent back) ──
state = st.session_state.site_state
site_area = state.get("site_area")
built_area = state.get("built_area")
util_pct = state.get("utilization_pct")

if site_area is not None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Site area", f"{site_area:.0f} m²")
    c2.metric("Built area", f"{built_area:.0f} m²")
    c3.metric("Utilisation", f"{util_pct:.1f}%")
    c4.metric("Buildings", f"{len(state.get('buildings', []))}")
