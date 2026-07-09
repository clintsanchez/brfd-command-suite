"""Shared helpers for the BRFD Command Suite Streamlit app."""
import os, sys, subprocess
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
ANALYSIS = ROOT / "analysis"
OUTPUT = ANALYSIS / "output"
for p in (str(ROOT), str(ANALYSIS)):     # import firstdue_mcp, brla, reference, analyses
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Bridge Streamlit Cloud secrets -> env vars so the First Due client (reads os.environ) works
# on hosted deploys where you set secrets in the platform UI instead of committing a .env.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass


def require_auth():
    """Password gate. Active only when APP_PASSWORD is set (env or st.secrets) — so local/LAN
    runs stay open, but any hosted deploy is protected. Call at the top of every page."""
    pw = os.environ.get("APP_PASSWORD")
    if not pw:
        return
    if st.session_state.get("_authed"):
        return
    st.markdown("## 🔒 BRFD Command Suite")
    st.caption("Restricted — internal fire-department data.")
    entered = st.text_input("Password", type="password")
    if entered:
        if entered == pw:
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


@st.cache_resource
def get_client():
    from firstdue_mcp.client import FirstDueClient
    return FirstDueClient(timeout=90)


def embed(filename, height=620):
    """Embed a generated self-contained HTML report/map from analysis/output/."""
    p = OUTPUT / filename
    if p.exists():
        components.html(p.read_text(encoding="utf-8"), height=height, scrolling=True)
        st.caption(f"Source: analysis/output/{filename}")
    else:
        st.info(f"Not generated yet ({filename}). Use the button below to build it.")


def regenerate(script, args=None, label=None, slow=False):
    """Button that runs an analysis script (in analysis/) as a subprocess."""
    if slow:
        st.caption("⏳ Slow — pulls a lot of data / heavy compute.")
    if st.button(label or f"Regenerate ({script})", key=f"regen_{script}"):
        with st.spinner(f"Running {script} …"):
            r = subprocess.run([sys.executable, str(ANALYSIS / script)] + (args or []),
                               capture_output=True, text=True, cwd=str(ANALYSIS))
        tail = (r.stderr or "") + (r.stdout or "")
        if r.returncode == 0:
            st.success("Done — refresh below.")
            st.code(tail[-1800:] or "ok")
            st.rerun()
        else:
            st.error(f"Failed (exit {r.returncode}).")
            st.code(tail[-2500:])
