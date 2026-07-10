import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from lib import embed, regenerate, require_auth

require_auth()
st.title("🏘️ Community Risk & CRR Targeting")
st.caption("Social Vulnerability Index × smoke-alarm coverage — where to send the next canvass.")

tab1, tab2, tab3 = st.tabs(["🎯 SVI × Smoke-Alarm", "SVI map", "ZIP gap"])

with tab1:
    st.markdown("**High social vulnerability + low completed installs = priority.** Dark tracts with "
                "no blue dots are the targets.")
    st.markdown("Upload your **Community Connect smoke-alarm export** (the CSV you download from First "
                "Due) and it builds the targeting map right here — no local files needed.")
    up = st.file_uploader("Community Connect export (CSV)", type=["csv"])

    if up is not None:
        import svi_smoke_overlay as ov   # analysis/ is on sys.path via lib
        try:
            with st.spinner("Geocoding installs and building the targeting map…"):
                m, targets, stats = ov.build_overlay(up)
            st.success(f"{stats['geocoded']:,} of {stats['installs']:,} installs mapped · "
                       f"{stats['zero_installs']} of {stats['high_svi']} high-vulnerability tracts (SVI≥0.80) "
                       f"have **zero** completed installs.")
            components.html(m._repr_html_(), height=620, scrolling=True)
            if targets:
                st.markdown("**Priority tracts** (high SVI, fewest installs):")
                st.dataframe(pd.DataFrame(targets), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Couldn't build the map: {e}")
    else:
        st.caption("No file uploaded yet — showing the last locally-generated map, if one exists.")
        embed("BRFD_SVI_SmokeAlarm_Overlay.html", height=620)

with tab2:
    st.markdown("Social Vulnerability Index by census tract (CDC/ATSDR via data.brla.gov).")
    st.caption("☁️ Works anywhere — pulls tract geometry live from data.brla.gov.")
    embed("BRFD_SVI_Map.html", height=600)
    regenerate("svi_map.py", label="Regenerate SVI map")

with tab3:
    st.markdown("Smoke-alarm installs vs. senior population by ZIP.")
    st.caption("Upload the same Community Connect CSV in the first tab for the tract-level version; "
               "this ZIP breakdown runs from the command line (`smoke_alarm_gap.py`).")
