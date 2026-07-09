"""BRFD Command Suite — Streamlit app entry point.  Run:  streamlit run app/Home.py"""
import datetime as dt
import streamlit as st
from lib import get_client, require_auth

st.set_page_config(page_title="BRFD Command Suite", page_icon="🚒", layout="wide")
require_auth()

st.title("🚒 BRFD Command Suite")
st.caption("Unified analytics over the First Due RMS and Baton Rouge open data — "
           "incidents, dispatch, response coverage, community risk, training, hydrants.")


@st.cache_data(ttl=900, show_spinner="Loading live figures from First Due…")
def overview():
    c = get_client()
    year = dt.date.today().year
    out = {}
    try:
        out["ytd"] = c.list_fire_incidents(start_alarm_at=f"{year}-01-01T00:00:00Z", page=1).get("total")
    except Exception:
        out["ytd"] = None
    try:
        wk = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        out["week"] = c.list_fire_incidents(start_alarm_at=f"{wk}T00:00:00Z", page=1).get("total")
    except Exception:
        out["week"] = None
    try:
        out["stations"] = c.list_stations().get("total")
    except Exception:
        out["stations"] = None
    try:
        out["personnel"] = c.list_personnel().get("total")
    except Exception:
        out["personnel"] = None
    return out


kpi = overview()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Incidents YTD", f"{kpi['ytd']:,}" if kpi["ytd"] else "—")
c2.metric("Incidents (last 7 days)", f"{kpi['week']:,}" if kpi["week"] else "—")
c3.metric("Stations", kpi["stations"] or "—")
c4.metric("Personnel", kpi["personnel"] or "—")

st.divider()
st.subheader("What's inside")
st.markdown(
    "- **🔥 Incidents & Hotspots** — query incidents by date; H3 call-density map\n"
    "- **⏱️ Response & Dispatch** — NFPA-1710 alarm-handling analysis + station drive-time coverage\n"
    "- **🏘️ Community Risk** — Social Vulnerability Index × smoke-alarm coverage (CRR targeting)\n"
    "- **🎓 Training** — program overview, completion, participation\n"
    "- **🚰 Hydrants** — live status, out-of-service list\n\n"
    "Use the sidebar to navigate. Each page can **regenerate** its analysis and, where relevant, "
    "produces a shareable self-contained HTML file in `analysis/output/`."
)
st.info("Live data uses your First Due token from `.env`. Endpoints your license doesn't cover show as “—”.")
