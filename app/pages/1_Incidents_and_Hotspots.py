import datetime as dt
from collections import Counter

import pandas as pd
import streamlit as st
from lib import get_client, embed, regenerate, require_auth
from reference.nfirs import label, category

require_auth()
st.title("🔥 Incidents & Hotspots")

c1, c2 = st.columns(2)
start = c1.date_input("From", dt.date.today() - dt.timedelta(days=30))
end = c2.date_input("To", dt.date.today() + dt.timedelta(days=1))

if st.button("Query incidents", type="primary"):
    client = get_client()
    try:
        env = client.list_fire_incidents(start_alarm_at=f"{start}T00:00:00Z",
                                          end_alarm_at=f"{end}T00:00:00Z", page=1)
    except Exception as e:
        st.error(str(e)); st.stop()
    rows = env.get("fire_incidents", [])
    a, b = st.columns(2)
    a.metric("Total in range", f"{env.get('total', 0):,}")
    b.metric("Pages (500/page)", env.get("pages"))
    if rows:
        cats = Counter(category(r.get("actual_incident_type")) for r in rows)
        st.subheader(f"Category mix (first {len(rows)} of {env.get('total', 0):,})")
        st.bar_chart(pd.Series(cats).sort_values(ascending=False))
        types = Counter(f"{r.get('actual_incident_type')} · {label(r.get('actual_incident_type'))}" for r in rows)
        st.dataframe(pd.DataFrame(types.most_common(15), columns=["NFIRS type", "Count"]),
                     use_container_width=True, hide_index=True)

st.divider()
st.subheader("Call-density hotspot map")
embed("BRFD_Incident_Hotspots.html", height=560)
regenerate("incident_hotspots.py", label="Regenerate hotspot map (~2 months)")
