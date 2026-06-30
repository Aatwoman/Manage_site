"""
Construction Site Planner  ·  v4.0 (rebuilt for reliability)
─────────────────────────────────────────────────────────────────────────────
A deliberately small, robust rewrite. Everything interactive (dragging
buildings, dragging/resizing the boundary, editing names & thresholds) lives
inside one Streamlit Custom Component (components/canvas/index.html), built
with plain JavaScript and Streamlit's own supported component protocol
(Streamlit.setComponentValue), instead of the previous version's hand-rolled
postMessage/DOM-hunting hack. That hack was the source of most crashes.

Python's job is now just: hold the current layout in session_state, show it
to the component, receive updates back, display summary stats, and offer
save/load as JSON. No shapely, no pandas, no custom geometry duplicated here.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import os
import copy

import streamlit as st
import streamlit.components.v1 as components

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Site Planner", page_icon="🏗️", layout="wide")

# ─────────────────────────────────────────────────────────────
# COMPONENT DECLARATION
# ─────────────────────────────────────────────────────────────
_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "canvas")
_site_canvas = components.declare_component("site_canvas", path=_COMPONENT_DIR)


def site_canvas(version: int, initial_state: dict, key: str | None = None):
    return _site_canvas(version=version, initial_state=initial_state, key=key, default=None)


# ─────────────────────────────────────────────────────────────
# DEFAULT STATE
# ─────────────────────────────────────────────────────────────
DEFAULT_STATE = {
    "boundary": {"preset": "rectangle", "x": 15, "y": 15, "w": 150, "h": 95},
    "buildings": [],
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
    version=st.session_state.version,
    initial_state=st.session_state.site_state,
    key="canvas",
)
if result is not None:
    st.session_state.site_state = result

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
