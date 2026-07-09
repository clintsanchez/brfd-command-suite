import streamlit as st
from lib import embed, regenerate, require_auth

require_auth()
st.title("🏘️ Community Risk & CRR Targeting")
st.caption("Social Vulnerability Index × smoke-alarm coverage — where to send the next canvass.")

tab1, tab2, tab3 = st.tabs(["🎯 SVI × Smoke-Alarm", "SVI map", "ZIP gap"])

with tab1:
    st.markdown("**High social vulnerability + low completed installs = priority.** Dark tracts with "
                "no blue dots are the targets.")
    embed("BRFD_SVI_SmokeAlarm_Overlay.html", height=620)
    regenerate("svi_smoke_overlay.py", label="Regenerate targeting map (geocodes installs)")

with tab2:
    st.markdown("Social Vulnerability Index by census tract (CDC/ATSDR via data.brla.gov).")
    embed("BRFD_SVI_Map.html", height=600)
    regenerate("svi_map.py", label="Regenerate SVI map")

with tab3:
    st.markdown("Smoke-alarm installs vs. senior population by ZIP (prints a ranked table to the log).")
    regenerate("smoke_alarm_gap.py", label="Run ZIP gap analysis")
