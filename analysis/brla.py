"""
Baton Rouge open-data client (data.brla.gov).

data.brla.gov runs on Socrata — every dataset has a REST API, no auth needed for reads
(an optional SOCRATA_APP_TOKEN raises rate limits). Two access patterns:
  - tabular data  -> /resource/{id}.json  (SoQL: where=, select=, order=, q=, ...)
  - geospatial    -> /api/geospatial/{id}?method=export&format=GeoJSON

    import brla
    rows = brla.get_rows("dakq-4sda", where="alarm_date > '2026-01-01'", limit=1000)
    gj   = brla.get_geojson("q7v5-ijjg")          # SVI tracts with geometry
    for d in brla.search_catalog("fire"): print(d["id"], d["name"])

Handy dataset IDs (data.brla.gov):
  dakq-4sda  Baton Rouge Fire Incidents        h453-hp7u  BRFD Occupancy Inspections
  puvg-q6uk  BRFD Hazmat Incidents             5fcu-7qaq  Fire District (geo)
  h667-2xhn  Fire/EMS Station locations        q7v5-ijjg  Social Vulnerability Index (geo)
  i6q4-ime9  Building Footprint (geo)          489u-eq9d  Tax Parcel (geo)
  a4h4-zi7e  Adjudicated (blighted) Property   68hc-v6h3  Flood Hazard Area (geo)
  522a-c6dn  CDC PLACES health by ZIP          7wah-qncc  Traffic Crash Incidents
"""
import os
import requests

BASE = "https://data.brla.gov"
_TOKEN = os.environ.get("SOCRATA_APP_TOKEN")


def _headers():
    return {"X-App-Token": _TOKEN} if _TOKEN else {}


def get_rows(dataset_id, limit=50000, **soql):
    """Tabular rows via SODA. Keyword args become SoQL `$` params
    (e.g. where="...", select="...", order="...", q="..."). Returns a list of dicts."""
    params = {"$limit": limit}
    for k, v in soql.items():
        params[f"${k}"] = v
    r = requests.get(f"{BASE}/resource/{dataset_id}.json", params=params, headers=_headers(), timeout=90)
    r.raise_for_status()
    return r.json()


def get_geojson(dataset_id, timeout=120):
    """Geospatial layer exported as a GeoJSON FeatureCollection (dict)."""
    r = requests.get(f"{BASE}/api/geospatial/{dataset_id}",
                     params={"method": "export", "format": "GeoJSON"},
                     headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def search_catalog(query=None, limit=400):
    """List/search datasets on data.brla.gov. Returns [{id, name, description}]."""
    params = {"domains": "data.brla.gov", "search_context": "data.brla.gov", "limit": limit}
    if query:
        params["q"] = query
    r = requests.get(f"{BASE}/api/catalog/v1", params=params, headers=_headers(), timeout=90)
    r.raise_for_status()
    out = []
    for x in r.json().get("results", []):
        if x.get("metadata", {}).get("domain") == "data.brla.gov":
            res = x.get("resource", {})
            out.append({"id": res.get("id"), "name": res.get("name"), "description": res.get("description")})
    return out


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "fire"
    for d in search_catalog(q):
        print(f"{d['id']:<12} {d['name']}")
