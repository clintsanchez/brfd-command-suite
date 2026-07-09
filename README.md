# BRFD Command Suite

Interactive analytics app (Streamlit) over the First Due RMS and Baton Rouge open data —
incidents & hotspots, NFPA-1710 dispatch/response, community-risk (SVI × smoke-alarm) targeting,
training, and hydrants.

This is the **public deploy repo** — app source only. It contains **no credentials, no internal
documents, and no resident data**. At runtime it reads two secrets you provide via the host:

```toml
FIRSTDUE_API_TOKEN = "…"   # First Due API token
APP_PASSWORD       = "…"   # login for the app
```

## Run locally
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# set the two vars (or a local .env), then:
.venv/Scripts/python -m streamlit run app/Home.py
```

## Deploy (Streamlit Community Cloud)
Main file path: `app/Home.py` · add the two secrets above under **Advanced settings → Secrets**.

Heavy geospatial map generation (station coverage via osmnx) is a local-only step; see
`analysis/requirements.txt`.
