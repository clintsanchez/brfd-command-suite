import streamlit as st
from lib import embed, regenerate, require_auth

require_auth()
st.title("🎓 Training")
st.caption("Program overview — sessions, topics, completion, participation (First Due activity log).")

embed("BRFD_Training_Analysis.html", height=700)
regenerate("training_report.py", label="Regenerate training report (YTD)")
