"""
Construction Site Planner — Streamlit App
Manages building placement, site boundary, safety clearances, and space utilisation.
"""

import json
import math
import uuid
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from shapely.affinity import rotate, translate
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Site Planner",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CONSTANTS & COLOUR PALETTE
# ─────────────────────────────────────────────
CATEGORY_COLORS = {
    "Office / Admin": "#4A90D9",
    "Warehouse": "#E07B39",
    "Workshop / Lab": "#6BBF59",
    "Storage Yard": "#9B59B6",
    "Utility / Plant Room": "#F1C40F",
    "Access Road": "#95A5A6",
    "Green / Landscape": "#27AE60",
    "Custom": "#E74C3C",
}

SHAPE_TYPES = ["Rectangle", "L-Shape", "T-Shape", "Hexagon", "Custom Polygon"]

DEFAULT_SITE_BOUNDARY = [(0, 0), (100, 0), (100, 80), (60, 80), (60, 60), (0, 60)]


# ─────────────────────────────────────────────
# SESSION STATE BOOTSTRAP
# ─────────────────────────────────────────────
def init_state():
    defaults = {
        "buildings": {},           # id -> dict
        "site_vertices": list(DEFAULT_SITE_BOUNDARY),
        "safety_margin": 2.0,      # minimum gap between structures (m)
        "boundary_threshold": 1.5, # minimum gap to site edge (m)
        "selected_id": None,
        "edit_mode": "view",       # view | add | edit_building | edit_boundary
        "show_safety_zones": True,
        "show_utilisation": True,
        "snap_grid": 1.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ─────────────────────────────────────────────
# GEOMETRY HELPERS
# ─────────────────────────────────────────────
def make_rectangle(x, y, w, h, angle=0.0) -> Polygon:
    rect = Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    return rotate(rect, angle, origin=(x + w / 2, y + h / 2))


def make_l_shape(x, y, w, h, stem_w, stem_h, angle=0.0) -> Polygon:
    pts = [
        (x, y), (x + w, y), (x + w, y + stem_h),
        (x + stem_w, y + stem_h), (x + stem_w, y + h), (x, y + h),
    ]
    poly = Polygon(pts)
    return rotate(poly, angle, origin=(x + w / 2, y + h / 2))


def make_t_shape(x, y, w, h, cap_h, angle=0.0) -> Polygon:
    stem_w = w / 3
    stem_x = x + w / 3
    pts = [
        (x, y + cap_h), (x + w, y + cap_h), (x + w, y),
        (x, y),
        # back up into stem
        (x, y + cap_h), (stem_x, y + cap_h),
        (stem_x, y + h), (stem_x + stem_w, y + h),
        (stem_x + stem_w, y + cap_h), (x + w, y + cap_h),
    ]
    # simpler: compose from two rectangles
    top = Polygon([(x, y), (x + w, y), (x + w, y + cap_h), (x, y + cap_h)])
    stem = Polygon([
        (stem_x, y + cap_h), (stem_x + stem_w, y + cap_h),
        (stem_x + stem_w, y + h), (stem_x, y + h),
    ])
    poly = top.union(stem)
    return rotate(poly, angle, origin=(x + w / 2, y + h / 2))


def make_hexagon(cx, cy, radius, angle=0.0) -> Polygon:
    pts = [
        (cx + radius * math.cos(math.radians(60 * i)),
         cy + radius * math.sin(math.radians(60 * i)))
        for i in range(6)
    ]
    poly = Polygon(pts)
    return rotate(poly, angle, origin=(cx, cy))


def building_polygon(b: dict) -> Polygon:
    """Reconstruct a Shapely polygon from a building dict."""
    s = b["shape"]
    x, y, angle = b["x"], b["y"], b.get("angle", 0.0)

    if s == "Rectangle":
        return make_rectangle(x, y, b["width"], b["height"], angle)
    elif s == "L-Shape":
        return make_l_shape(x, y, b["width"], b["height"],
                            b.get("stem_w", b["width"] / 2),
                            b.get("stem_h", b["height"] / 2), angle)
    elif s == "T-Shape":
        return make_t_shape(x, y, b["width"], b["height"],
                            b.get("cap_h", b["height"] / 3), angle)
    elif s == "Hexagon":
        return make_hexagon(x + b["radius"], y + b["radius"], b["radius"], angle)
    elif s == "Custom Polygon":
        if len(b.get("custom_pts", [])) >= 3:
            return rotate(Polygon(b["custom_pts"]), angle,
                          origin=Polygon(b["custom_pts"]).centroid)
        return Polygon()
    return Polygon()


def site_polygon() -> Polygon:
    verts = st.session_state.site_vertices
    if len(verts) >= 3:
        return Polygon(verts)
    return Polygon()


def snap(val, grid):
    if grid <= 0:
        return val
    return round(val / grid) * grid


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────
def check_collisions(target_id: str, poly: Polygon) -> list[str]:
    """Return list of building IDs that collide with `poly` (excluding target)."""
    margin = st.session_state.safety_margin
    hits = []
    for bid, b in st.session_state.buildings.items():
        if bid == target_id:
            continue
        other = building_polygon(b)
        if poly.buffer(margin / 2).intersects(other.buffer(margin / 2)):
            hits.append(b["name"])
    return hits


def check_boundary(poly: Polygon) -> bool:
    """True if poly fits inside site with required boundary threshold."""
    site = site_polygon()
    if site.is_empty:
        return True
    threshold = st.session_state.boundary_threshold
    return site.buffer(-threshold).contains(poly)


# ─────────────────────────────────────────────
# PLOT
# ─────────────────────────────────────────────
def build_figure() -> go.Figure:
    fig = go.Figure()
    site = site_polygon()

    # ── Site boundary ──────────────────────────
    if not site.is_empty:
        sx, sy = site.exterior.xy
        fig.add_trace(go.Scatter(
            x=list(sx), y=list(sy), fill="toself",
            fillcolor="rgba(220,230,240,0.3)",
            line=dict(color="#2C3E50", width=2.5, dash="dash"),
            name="Site Boundary", hoverinfo="skip",
        ))
        # Threshold inset
        inset = site.buffer(-st.session_state.boundary_threshold)
        if not inset.is_empty and not inset.geom_type == "Point":
            geoms = [inset] if inset.geom_type == "Polygon" else list(inset.geoms)
            for g in geoms:
                ix, iy = g.exterior.xy
                fig.add_trace(go.Scatter(
                    x=list(ix), y=list(iy),
                    line=dict(color="#E74C3C", width=1, dash="dot"),
                    mode="lines", name="Boundary Threshold",
                    hoverinfo="skip", showlegend=False,
                ))

    # ── Buildings ─────────────────────────────
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        if poly.is_empty:
            continue

        is_selected = (bid == st.session_state.selected_id)
        color = b.get("color", "#4A90D9")
        alpha = "cc" if is_selected else "99"

        geoms = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
        for g in geoms:
            px, py = g.exterior.xy
            fig.add_trace(go.Scatter(
                x=list(px), y=list(py), fill="toself",
                fillcolor=color + alpha,
                line=dict(color=color, width=3 if is_selected else 1.5),
                name=b["name"],
                text=f"<b>{b['name']}</b><br>Category: {b['category']}<br>Area: {poly.area:.1f} m²",
                hoverinfo="text",
                hoverlabel=dict(bgcolor="white", font_size=12),
            ))

        # Safety buffer ring
        if st.session_state.show_safety_zones:
            margin = st.session_state.safety_margin
            buf = poly.buffer(margin)
            bgeoms = [buf] if buf.geom_type == "Polygon" else list(buf.geoms)
            for bg in bgeoms:
                bx, by_ = bg.exterior.xy
                fig.add_trace(go.Scatter(
                    x=list(bx), y=list(by_),
                    line=dict(color=color + "55", width=1, dash="dot"),
                    fill="toself", fillcolor=color + "18",
                    mode="lines", hoverinfo="skip", showlegend=False,
                ))

        # Label at centroid
        cx, cy_ = poly.centroid.x, poly.centroid.y
        fig.add_trace(go.Scatter(
            x=[cx], y=[cy_], mode="text",
            text=[b["name"]],
            textfont=dict(size=10, color="#1a1a1a", family="monospace"),
            hoverinfo="skip", showlegend=False,
        ))

    # ── Layout ────────────────────────────────
    fig.update_layout(
        plot_bgcolor="#F7F9FC",
        paper_bgcolor="#F7F9FC",
        showlegend=False,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(
            showgrid=True, gridcolor="#E0E6F0", gridwidth=1,
            zeroline=False, scaleanchor="y", scaleratio=1,
            title="X (metres)",
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#E0E6F0", gridwidth=1,
            zeroline=False, title="Y (metres)",
        ),
        dragmode="pan",
        height=620,
    )
    return fig


# ─────────────────────────────────────────────
# UTILISATION STATS
# ─────────────────────────────────────────────
def utilisation_stats() -> dict:
    site = site_polygon()
    site_area = site.area if not site.is_empty else 0

    polys = []
    for b in st.session_state.buildings.values():
        p = building_polygon(b)
        if not p.is_empty:
            polys.append(p)

    built_union = unary_union(polys) if polys else Polygon()
    built_area = built_union.area

    # Area inside site
    inside = built_union.intersection(site).area if not site.is_empty else built_area

    return {
        "site_area": site_area,
        "built_area": built_area,
        "inside_area": inside,
        "utilisation_pct": (inside / site_area * 100) if site_area > 0 else 0,
        "free_area": max(0, site_area - inside),
        "n_buildings": len(st.session_state.buildings),
    }


# ─────────────────────────────────────────────
# IMPORT / EXPORT
# ─────────────────────────────────────────────
def export_state() -> str:
    payload = {
        "site_vertices": st.session_state.site_vertices,
        "safety_margin": st.session_state.safety_margin,
        "boundary_threshold": st.session_state.boundary_threshold,
        "buildings": st.session_state.buildings,
    }
    return json.dumps(payload, indent=2)


def import_state(raw: str):
    data = json.loads(raw)
    st.session_state.site_vertices = [tuple(v) for v in data.get("site_vertices", DEFAULT_SITE_BOUNDARY)]
    st.session_state.safety_margin = data.get("safety_margin", 2.0)
    st.session_state.boundary_threshold = data.get("boundary_threshold", 1.5)
    st.session_state.buildings = data.get("buildings", {})


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
def render_sidebar():
    st.sidebar.title("🏗️ Site Planner")
    st.sidebar.caption("Construction Layout Tool")
    st.sidebar.divider()

    # ── Safety parameters ─────────────────────
    st.sidebar.subheader("🛡️ Safety Parameters")
    st.session_state.safety_margin = st.sidebar.slider(
        "Safety clearance between structures (m)",
        min_value=0.0, max_value=10.0,
        value=st.session_state.safety_margin, step=0.5,
    )
    st.session_state.boundary_threshold = st.sidebar.slider(
        "Boundary setback (m)",
        min_value=0.0, max_value=15.0,
        value=st.session_state.boundary_threshold, step=0.5,
    )
    st.session_state.snap_grid = st.sidebar.select_slider(
        "Snap-to-grid (m)", options=[0.0, 0.5, 1.0, 2.0, 5.0],
        value=st.session_state.snap_grid,
    )
    st.sidebar.divider()

    # ── View toggles ─────────────────────────
    st.sidebar.subheader("👁️ Display")
    st.session_state.show_safety_zones = st.sidebar.toggle(
        "Show safety buffer zones", value=st.session_state.show_safety_zones
    )
    st.session_state.show_utilisation = st.sidebar.toggle(
        "Show utilisation panel", value=st.session_state.show_utilisation
    )
    st.sidebar.divider()

    # ── Import / Export ───────────────────────
    st.sidebar.subheader("💾 Save / Load")
    if st.sidebar.button("📥 Export layout (JSON)", use_container_width=True):
        st.sidebar.download_button(
            "Download layout.json",
            data=export_state(),
            file_name="site_layout.json",
            mime="application/json",
            use_container_width=True,
        )

    uploaded = st.sidebar.file_uploader("Import layout JSON", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            import_state(uploaded.read().decode())
            st.success("Layout imported.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Import failed: {e}")

    st.sidebar.divider()
    st.sidebar.caption("v1.0 · Built with Streamlit + Shapely + Plotly")


# ─────────────────────────────────────────────
# BUILDING FORM
# ─────────────────────────────────────────────
def render_add_edit_form(existing_id: Optional[str] = None):
    is_edit = existing_id is not None
    b = st.session_state.buildings.get(existing_id, {}) if is_edit else {}

    st.subheader("✏️ Edit Structure" if is_edit else "➕ Add Structure")

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value=b.get("name", f"Building {len(st.session_state.buildings)+1}"))
        category = st.selectbox("Category", list(CATEGORY_COLORS.keys()),
                                index=list(CATEGORY_COLORS.keys()).index(b.get("category", "Office / Admin")))
        color = st.color_picker("Colour", value=b.get("color", CATEGORY_COLORS[category]))

    with col2:
        shape = st.selectbox("Shape", SHAPE_TYPES,
                             index=SHAPE_TYPES.index(b.get("shape", "Rectangle")))
        angle = st.slider("Rotation (°)", -180, 180, int(b.get("angle", 0)), step=5)
        notes = st.text_area("Notes", value=b.get("notes", ""), height=68)

    st.divider()
    grid = st.session_state.snap_grid

    # ── Shape-specific parameters ─────────────
    params = {}
    if shape == "Rectangle":
        c1, c2, c3, c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X origin (m)", value=float(b.get("x", 10.0)), step=grid or 1.0), grid)
        params["y"]      = snap(c2.number_input("Y origin (m)", value=float(b.get("y", 10.0)), step=grid or 1.0), grid)
        params["width"]  = snap(c3.number_input("Width (m)", value=float(b.get("width", 20.0)), min_value=1.0, step=grid or 1.0), grid)
        params["height"] = snap(c4.number_input("Height (m)", value=float(b.get("height", 15.0)), min_value=1.0, step=grid or 1.0), grid)

    elif shape == "L-Shape":
        c1, c2, c3, c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X", value=float(b.get("x", 10.0)), step=grid or 1.0), grid)
        params["y"]      = snap(c2.number_input("Y", value=float(b.get("y", 10.0)), step=grid or 1.0), grid)
        params["width"]  = snap(c3.number_input("Overall W (m)", value=float(b.get("width", 20.0)), min_value=2.0, step=grid or 1.0), grid)
        params["height"] = snap(c4.number_input("Overall H (m)", value=float(b.get("height", 15.0)), min_value=2.0, step=grid or 1.0), grid)
        c5, c6 = st.columns(2)
        params["stem_w"] = snap(c5.number_input("Stem width (m)", value=float(b.get("stem_w", 10.0)), min_value=1.0, step=grid or 1.0), grid)
        params["stem_h"] = snap(c6.number_input("Stem height (m)", value=float(b.get("stem_h", 8.0)), min_value=1.0, step=grid or 1.0), grid)

    elif shape == "T-Shape":
        c1, c2, c3, c4 = st.columns(4)
        params["x"]      = snap(c1.number_input("X", value=float(b.get("x", 10.0)), step=grid or 1.0), grid)
        params["y"]      = snap(c2.number_input("Y", value=float(b.get("y", 10.0)), step=grid or 1.0), grid)
        params["width"]  = snap(c3.number_input("Total W (m)", value=float(b.get("width", 30.0)), min_value=3.0, step=grid or 1.0), grid)
        params["height"] = snap(c4.number_input("Total H (m)", value=float(b.get("height", 20.0)), min_value=2.0, step=grid or 1.0), grid)
        params["cap_h"]  = snap(st.number_input("Cap height (m)", value=float(b.get("cap_h", 8.0)), min_value=1.0, step=grid or 1.0), grid)

    elif shape == "Hexagon":
        c1, c2, c3 = st.columns(3)
        params["x"]      = snap(c1.number_input("Centre X (m)", value=float(b.get("x", 20.0)), step=grid or 1.0), grid)
        params["y"]      = snap(c2.number_input("Centre Y (m)", value=float(b.get("y", 20.0)), step=grid or 1.0), grid)
        params["radius"] = snap(c3.number_input("Radius (m)", value=float(b.get("radius", 8.0)), min_value=1.0, step=grid or 1.0), grid)

    elif shape == "Custom Polygon":
        st.info("Enter comma-separated X,Y pairs — one per line. E.g.  `10,10`")
        default_pts = b.get("custom_pts", [(10, 10), (30, 10), (30, 25), (10, 25)])
        raw_pts = st.text_area(
            "Vertices (X,Y per line)",
            value="\n".join(f"{p[0]},{p[1]}" for p in default_pts),
            height=120,
        )
        parsed = []
        for line in raw_pts.strip().splitlines():
            try:
                px, py = line.split(",")
                parsed.append((float(px.strip()), float(py.strip())))
            except ValueError:
                pass
        params["custom_pts"] = parsed
        params["x"] = parsed[0][0] if parsed else 0
        params["y"] = parsed[0][1] if parsed else 0

    params["shape"]    = shape
    params["angle"]    = float(angle)
    params["name"]     = name
    params["category"] = category
    params["color"]    = color
    params["notes"]    = notes

    # ── Preview ───────────────────────────────
    preview_poly = building_polygon(params)
    if not preview_poly.is_empty:
        area = preview_poly.area
        bbox = preview_poly.bounds
        st.caption(f"Preview — Area: **{area:.1f} m²** · Bounding box: {bbox[2]-bbox[0]:.1f} × {bbox[3]-bbox[1]:.1f} m")

    # ── Save ─────────────────────────────────
    save_col, cancel_col, *_ = st.columns([1, 1, 3])
    save_label = "💾 Save Changes" if is_edit else "➕ Place Structure"
    if save_col.button(save_label, type="primary", use_container_width=True):
        bid = existing_id or str(uuid.uuid4())[:8]
        poly = building_polygon(params)

        collisions = check_collisions(bid, poly)
        in_boundary = check_boundary(poly)

        warnings = []
        if collisions:
            warnings.append(f"⚠️ Safety clearance violated with: {', '.join(collisions)}")
        if not in_boundary:
            warnings.append("⚠️ Structure breaches boundary setback.")

        if warnings:
            for w in warnings:
                st.warning(w)
            if not st.session_state.get("force_place"):
                st.session_state["force_place"] = True
                st.info("Press **Save** again to place anyway.")
                return
        st.session_state.pop("force_place", None)
        st.session_state.buildings[bid] = params
        st.session_state.selected_id = bid
        st.session_state.edit_mode = "view"
        st.success(f"✅ '{name}' placed." if not is_edit else f"✅ '{name}' updated.")
        st.rerun()

    if cancel_col.button("Cancel", use_container_width=True):
        st.session_state.edit_mode = "view"
        st.session_state.pop("force_place", None)
        st.rerun()


# ─────────────────────────────────────────────
# BOUNDARY EDITOR
# ─────────────────────────────────────────────
def render_boundary_editor():
    st.subheader("🗺️ Edit Site Boundary")
    st.info("Define the site outline as a list of X,Y vertices. Minimum 3 points. The polygon will close automatically.")

    current = st.session_state.site_vertices
    raw = st.text_area(
        "Vertices (X,Y per line)",
        value="\n".join(f"{p[0]},{p[1]}" for p in current),
        height=200,
    )
    parsed = []
    for line in raw.strip().splitlines():
        try:
            px, py = line.split(",")
            parsed.append((float(px.strip()), float(py.strip())))
        except ValueError:
            pass

    # Preset sites
    st.caption("— or load a preset —")
    presets = {
        "L-shaped site": [(0,0),(100,0),(100,40),(60,40),(60,80),(0,80)],
        "Rectangular site": [(0,0),(120,0),(120,80),(0,80)],
        "Irregular site": [(0,0),(90,0),(110,30),(100,70),(50,80),(0,60)],
        "T-shaped site": [(20,0),(80,0),(80,40),(100,40),(100,60),(80,60),(80,90),(20,90),(20,60),(0,60),(0,40),(20,40)],
    }
    preset_name = st.selectbox("Preset shapes", ["— none —"] + list(presets.keys()))
    if preset_name != "— none —":
        parsed = presets[preset_name]

    save_col, cancel_col, reset_col, _ = st.columns([1, 1, 1, 2])
    if save_col.button("💾 Apply Boundary", type="primary"):
        if len(parsed) < 3:
            st.error("Need at least 3 valid points.")
        else:
            st.session_state.site_vertices = parsed
            st.session_state.edit_mode = "view"
            st.success("Boundary updated.")
            st.rerun()
    if cancel_col.button("Cancel"):
        st.session_state.edit_mode = "view"
        st.rerun()
    if reset_col.button("↩ Reset to default"):
        st.session_state.site_vertices = list(DEFAULT_SITE_BOUNDARY)
        st.session_state.edit_mode = "view"
        st.rerun()

    # Live preview
    if len(parsed) >= 3:
        area = Polygon(parsed).area
        st.caption(f"Site area: **{area:.1f} m²** · {len(parsed)} vertices")


# ─────────────────────────────────────────────
# BUILDING TABLE
# ─────────────────────────────────────────────
def render_building_table():
    if not st.session_state.buildings:
        st.info("No structures placed yet. Click **Add Structure** to begin.")
        return

    rows = []
    for bid, b in st.session_state.buildings.items():
        poly = building_polygon(b)
        rows.append({
            "ID": bid,
            "Name": b["name"],
            "Category": b["category"],
            "Shape": b["shape"],
            "Area (m²)": f"{poly.area:.1f}",
            "Angle (°)": b.get("angle", 0),
            "Boundary ✓": "✅" if check_boundary(poly) else "⚠️",
            "Clearance ✓": "✅" if not check_collisions(bid, poly) else "⚠️",
        })

    df = pd.DataFrame(rows).set_index("ID")
    st.dataframe(df, use_container_width=True, height=220)

    # Select / delete
    sel_col, del_col = st.columns([3, 1])
    all_names = {b["name"]: bid for bid, b in st.session_state.buildings.items()}
    sel_name = sel_col.selectbox("Select to edit", ["— none —"] + list(all_names.keys()), label_visibility="collapsed")
    if sel_name != "— none —":
        sel_id = all_names[sel_name]
        if sel_col.button("✏️ Edit", use_container_width=False):
            st.session_state.selected_id = sel_id
            st.session_state.edit_mode = "edit_building"
            st.rerun()
        if del_col.button("🗑️ Delete", use_container_width=True):
            del st.session_state.buildings[sel_id]
            if st.session_state.selected_id == sel_id:
                st.session_state.selected_id = None
            st.rerun()


# ─────────────────────────────────────────────
# UTILISATION PANEL
# ─────────────────────────────────────────────
def render_utilisation():
    stats = utilisation_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Site Area", f"{stats['site_area']:.0f} m²")
    c2.metric("Built Area", f"{stats['inside_area']:.0f} m²")
    c3.metric("Free Area", f"{stats['free_area']:.0f} m²")
    c4.metric("Utilisation", f"{stats['utilisation_pct']:.1f}%")

    # Simple bar
    pct = stats["utilisation_pct"] / 100
    bar_html = f"""
    <div style="background:#e0e6f0;border-radius:6px;height:12px;margin-top:4px">
      <div style="background:{'#E07B39' if pct>0.85 else '#6BBF59'};width:{min(pct,1)*100:.1f}%;
                  height:100%;border-radius:6px;transition:width 0.4s"></div>
    </div>
    <p style="font-size:0.75rem;color:#555;margin-top:4px">
      {stats['n_buildings']} structure(s) placed
      {'— ⚠️ Over 85% utilisation' if pct>0.85 else ''}
    </p>
    """
    st.markdown(bar_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MAIN LAYOUT
# ─────────────────────────────────────────────
def main():
    render_sidebar()

    # ── Toolbar ───────────────────────────────
    t1, t2, t3, t4, t5 = st.columns([2, 2, 2, 2, 3])
    if t1.button("➕ Add Structure", type="primary", use_container_width=True):
        st.session_state.edit_mode = "add"
        st.session_state.selected_id = None
    if t2.button("🗺️ Edit Boundary", use_container_width=True):
        st.session_state.edit_mode = "edit_boundary"
    if t3.button("🗑️ Clear All", use_container_width=True):
        if st.session_state.buildings:
            st.session_state.buildings = {}
            st.session_state.selected_id = None
            st.rerun()
    if t4.button("⬇️ Export JSON", use_container_width=True):
        st.download_button(
            "💾 Download",
            data=export_state(),
            file_name="site_layout.json",
            mime="application/json",
        )

    # ── Mode panels ───────────────────────────
    if st.session_state.edit_mode == "add":
        render_add_edit_form()
        st.divider()
    elif st.session_state.edit_mode == "edit_building" and st.session_state.selected_id:
        render_add_edit_form(existing_id=st.session_state.selected_id)
        st.divider()
    elif st.session_state.edit_mode == "edit_boundary":
        render_boundary_editor()
        st.divider()

    # ── Utilisation banner ────────────────────
    if st.session_state.show_utilisation:
        render_utilisation()
        st.divider()

    # ── Main canvas ───────────────────────────
    st.plotly_chart(build_figure(), use_container_width=True, config={
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "toImageButtonOptions": {"format": "png", "filename": "site_layout"},
    })

    # ── Building table ────────────────────────
    st.subheader("📋 Structure List")
    render_building_table()


if __name__ == "__main__":
    main()
