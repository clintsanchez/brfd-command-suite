# Analysis scripts

Reusable analyses built on the First Due API client ([`../firstdue_mcp/client.py`](../firstdue_mcp/client.py)).
Each is standalone and portable: it resolves the repo root from its own location, loads
`../.env` for the API token, and writes outputs to `analysis/output/` (gitignored).

Run any of them with the project virtualenv:

```bash
../.venv/Scripts/python <script>.py        # Windows (Git Bash)
```

| Script | What it does | Output |
|--------|--------------|--------|
| `smoke_alarm_gap.py` | Smoke-alarm coverage vs. senior population by ZIP (Community Connect CSV × Census). Ranks neglected high-senior areas. | `output/smoke_alarm_gap.json` |
| `training_report.py` | Training program overview (sessions, topics, completion, participation) → shareable HTML. | `output/BRFD_Training_Analysis.html` |
| `dispatch_center_report.py` | Dispatch-center alarm-handling analysis vs NFPA 1710, with YoY, hour, call-type, day-of-week, concurrency → shareable HTML. | `output/BRFD_Dispatch_Center_Analysis.html` |
| `derive_dispatch_codes.py` | Utility: derive what each `dispatch_type_code` means from the data (cross-ref to NFIRS type). | prints to stdout |
| `incident_hotspots.py` | H3 hex-grid call-density hotspot map (labels top hexes via the NFIRS reference). | `output/BRFD_Incident_Hotspots.html` |
| `station_coverage.py` | NFPA-1710 drive-time coverage isochrones (4/8-min) per station + incident overlay → interactive map. | `output/BRFD_Station_Coverage.html` |
| `svi_targeting.py` | CDC/ATSDR Social Vulnerability Index for EBR tracts; ranks highest-need areas for CRR targeting. | `reference/svi_ebr_tracts.csv` |
| `svi_map.py` | SVI choropleth map (tract geometry from data.brla.gov) — visual companion to svi_targeting. | `output/BRFD_SVI_Map.html` |
| `svi_smoke_overlay.py` | **CRR targeting map:** geocodes smoke-alarm installs (Census) onto SVI tracts → finds high-vulnerability tracts with zero/low coverage. | `output/BRFD_SVI_SmokeAlarm_Overlay.html` |
| `brla.py` | **Baton Rouge open-data (data.brla.gov) client** — Socrata REST API (no auth): `get_rows()`, `get_geojson()`, `search_catalog()`. Handy dataset IDs in the module docstring. | *(library)* |

### Geospatial dependencies

`incident_hotspots.py`, `station_coverage.py`, and `svi_targeting.py` need the geo stack:

```bash
../.venv/Scripts/python -m pip install -r requirements.txt   # in this analysis/ folder
```

`station_coverage.py` downloads OpenStreetMap street data via an Overpass server. If the
default is unreachable, point it at a mirror:
`OVERPASS_URL=https://maps.mail.ru/osm/tools/overpass/api ../.venv/Scripts/python station_coverage.py`

Most scripts take optional date-range args, e.g.:

```bash
../.venv/Scripts/python training_report.py 2026-01-01 2026-07-08
../.venv/Scripts/python dispatch_center_report.py 2026 2025
```

## Data sources & scope notes

- **Training** comes from `GET /event-log/activities?module=Training`. Completion is
  recorded at the **session** level (no per-person pass/fail, no training-hours field);
  `fireStations`/`shifts` are unpopulated, so no per-station breakdown.
- **Dispatch timing** is computed from `/fire-incidents` (`alarm_at`) and each apparatus's
  `dispatch_at`. "Alarm" is when the call reaches First Due — it excludes 9-1-1
  ring/answer/transfer time at the primary PSAP. The call-processing usernames in the CAD
  log are **ProQA (medical) call-takers, not BRFD's own dispatchers**, so this cannot be
  split by individual BRFD dispatcher — that needs a CAD/PSAP export.
- **Smoke-alarm installs** are **not** in the API; export the report from the Community
  Connect module in the First Due UI as CSV. Senior population comes from the Census
  Reporter API (keyless, ACS 5-year, table B01001).

## PII

`smoke_alarm_gap.py` reads a Community Connect CSV that contains resident PII; it is read
locally only and produces **ZIP-aggregate** output. `.gitignore` blocks `*.csv`, `*.pdf`,
`*.xlsx`, and `analysis/output/` so no data or generated reports are committed. Keep it that way.
