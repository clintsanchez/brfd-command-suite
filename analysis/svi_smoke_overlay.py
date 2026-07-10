"""
SVI x smoke-alarm coverage overlay — the CRR targeting map.

Geocodes the Community Connect smoke-alarm requests (Census batch geocoder, free/no key),
drops them onto the SVI census tracts (from data.brla.gov), and finds the target gap:
HIGH social vulnerability + LOW/zero completed installs.

Two ways in:
  - CLI:  python svi_smoke_overlay.py [csv_path]   -> writes analysis/output/BRFD_SVI_SmokeAlarm_Overlay.html
  - App:  build_overlay(uploaded_file)             -> returns (folium.Map, targets, stats)  [used by the Streamlit app]

The input CSV contains resident PII; it's never persisted server-side beyond the rendered map
(which shows install *points*, status only, no names).
"""
import os, sys, csv, re, io
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
from dotenv import load_dotenv  # noqa: E402  (harmless locally; optional on cloud)
try:
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass
sys.path.insert(0, HERE)

import folium
import branca.colormap as cm
from shapely.geometry import shape, Point
import brla

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\csanchez\Downloads\Smoke Alarm Request Report.csv"
GEOCODER = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def num(x):
    try:
        v = float(x); return None if v == -999 else v
    except (TypeError, ValueError):
        return None


def load_rows(src):
    """Read CSV rows from a path (str) or an uploaded/file-like object -> list of row lists."""
    if hasattr(src, "getvalue"):            # Streamlit UploadedFile
        text = src.getvalue().decode("utf-8-sig", "replace")
    elif hasattr(src, "read"):              # any file object
        raw = src.read()
        text = raw.decode("utf-8-sig", "replace") if isinstance(raw, bytes) else raw
    else:                                   # path
        with open(src, newline="", encoding="utf-8-sig") as f:
            text = f.read()
    return list(csv.reader(io.StringIO(text)))


def parse_installs(rows):
    out = []
    for i, r in enumerate(rows[1:], 1):     # skip header
        if not r or not r[0].strip():
            continue
        parts = [p.strip() for p in (r[1] or "").split(",")]
        if len(parts) < 3:
            continue
        zc = re.search(r"\b(\d{5})\b", r[1]); zc = zc.group(1) if zc else ""
        out.append({"id": str(i), "street": parts[0], "city": parts[1] if len(parts) > 1 else "BATON ROUGE",
                    "state": "LA", "zip": zc, "status": (r[7] or "").strip() if len(r) > 7 else ""})
    return out


def geocode(rows):
    buf = io.StringIO(); w = csv.writer(buf)
    for r in rows:
        w.writerow([r["id"], r["street"], r["city"], r["state"], r["zip"]])
    resp = requests.post(GEOCODER, files={"addressFile": ("a.csv", buf.getvalue())},
                         data={"benchmark": "Public_AR_Current"}, timeout=180)
    resp.raise_for_status()
    coords = {}
    for row in csv.reader(io.StringIO(resp.text)):
        if len(row) >= 6 and row[2] == "Match" and row[5]:
            lon, lat = row[5].split(",")
            coords[row[0]] = (float(lat), float(lon))
    return coords


def build_overlay(src):
    """Core: from a CSV source, return (folium.Map, target_rows, stats dict)."""
    installs = parse_installs(load_rows(src))
    coords = geocode(installs)

    gj = brla.get_geojson("q7v5-ijjg")
    tracts = []
    for f in gj["features"]:
        p = f["properties"]
        p["pct_pov"] = round((num(p.get("ep_pov")) or 0) * 100)
        p["completed"] = 0
        tracts.append({"geom": shape(f["geometry"]), "fips": p.get("fips"),
                       "svi": num(p.get("rpl_themes")), "pct_pov": p["pct_pov"], "done_n": 0})
    by_fips = {t["fips"]: t for t in tracts}

    completed_pts = []
    for r in installs:
        c = coords.get(r["id"])
        if not c:
            continue
        done = r["status"] in ("Completed", "Reviewed")
        pt = Point(c[1], c[0])
        for t in tracts:
            if t["geom"].contains(pt):
                if done:
                    t["done_n"] += 1
                break
        if done:
            completed_pts.append(c)
    for f in gj["features"]:
        f["properties"]["completed"] = by_fips.get(f["properties"].get("fips"), {}).get("done_n", 0)

    ranked = sorted((t for t in tracts if t["svi"] is not None), key=lambda t: t["svi"], reverse=True)
    targets = [{"fips": t["fips"], "svi": round(t["svi"], 2), "pct_pov": t["pct_pov"], "installs": t["done_n"]}
               for t in sorted([t for t in ranked if t["svi"] >= 0.80], key=lambda t: (t["done_n"], -t["svi"]))]

    cmap = cm.linear.YlOrRd_09.scale(0, 1); cmap.caption = "SVI (higher = more vulnerable)"
    m = folium.Map(location=[30.45, -91.13], zoom_start=11, tiles="cartodbpositron")
    folium.GeoJson(gj, name="SVI",
                   style_function=lambda f: {"fillColor": cmap(num(f["properties"].get("rpl_themes")) or 0),
                                             "color": "#555", "weight": 0.4, "fillOpacity": 0.72},
                   tooltip=folium.GeoJsonTooltip(fields=["fips", "rpl_themes", "pct_pov", "completed"],
                       aliases=["Tract", "SVI", "% poverty", "Completed installs"])).add_to(m)
    fg = folium.FeatureGroup(name="Completed installs")
    for lat, lon in completed_pts:
        folium.CircleMarker([lat, lon], radius=2.5, color="#08519c", fill=True,
                            fill_color="#3182bd", fill_opacity=0.9, weight=0.5).add_to(fg)
    fg.add_to(m); cmap.add_to(m); folium.LayerControl().add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<h3 style='font-family:sans-serif'>Smoke-Alarm Coverage vs. Social Vulnerability</h3>"
        "<p style='font-family:sans-serif;color:#555'>Dark tracts = high vulnerability. Blue dots = "
        "completed installs. <b>Dark areas with no dots = priority CRR targets.</b></p>"))

    stats = {"installs": len(installs), "geocoded": len(coords),
             "high_svi": len([t for t in ranked if t["svi"] >= 0.80]),
             "zero_installs": len([t for t in targets if t["installs"] == 0])}
    return m, targets, stats


def main():
    if not os.path.exists(CSV_PATH):
        print("Community Connect export not found:\n  " + CSV_PATH +
              "\n\nThis targeting map needs the local smoke-alarm install CSV (resident PII — "
              "intentionally NOT in the repo or on the cloud server). Run it on a machine that has "
              "the export, pass the path (python svi_smoke_overlay.py <csv>), or use the upload box "
              "on the app's Community Risk page.")
        return
    m, targets, stats = build_overlay(CSV_PATH)
    out = os.path.join(OUT, "BRFD_SVI_SmokeAlarm_Overlay.html")
    m.save(out)
    print(f"installs {stats['installs']} | geocoded {stats['geocoded']} | "
          f"high-SVI tracts {stats['high_svi']} | of those with ZERO installs {stats['zero_installs']}")
    print("top targets:", [f"{t['fips']}(SVI {t['svi']}, {t['installs']} inst)" for t in targets[:5]])
    print("wrote", out)


if __name__ == "__main__":
    main()
