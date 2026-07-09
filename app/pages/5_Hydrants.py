import pandas as pd
import streamlit as st
from lib import get_client, require_auth

require_auth()
st.title("🚰 Hydrants")
st.caption("Live hydrant status from First Due. (`/get-hydrants` requires at least one filter.)")

col1, col2 = st.columns(2)
status = col1.selectbox("Status", ["out_of_service", "in_service"])
htype = col2.text_input("Type code (optional)", "")

if st.button("Query hydrants", type="primary"):
    client = get_client()
    try:
        env = client.list_hydrants(hydrant_status_code=status, hydrant_type_code=htype or None)
    except Exception as e:
        st.error(str(e)); st.stop()
    items = env.get("items", []) if isinstance(env, dict) else (env or [])
    total = env.get("total_hydrant_records") if isinstance(env, dict) else len(items)
    st.metric(f"{status.replace('_', ' ').title()} hydrants", f"{total:,}" if total else 0)
    if items:
        cols = ["fire_station", "fire_zone", "nearest_occupancy", "address",
                "reason_out_of_service", "inspected_at", "last_flow_tested_at"]
        df = pd.DataFrame(items)
        show = [c for c in cols if c in df.columns]
        st.dataframe(df[show] if show else df, use_container_width=True, hide_index=True)
        st.caption(f"Showing page 1 ({len(items)} of {total}). Full pagination available in the API client.")
