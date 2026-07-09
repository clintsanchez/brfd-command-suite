"""
SVI x smoke-alarm coverage overlay — the CRR targeting map.

Geocodes the Community Connect smoke-alarm requests (Census batch geocoder, free/no key),
drops them onto the SVI census tracts (from data.brla.gov), and finds the target gap:
HIGH social vulnerability + LOW/zero completed installs. Renders an interactive map
(SVI choropleth + completed-install points) and prints the priority tracts.

Input CSV contains resident PII -> read locally only; the output map shows install *points*
(status only, no names) and is gitignored. Usage: python svi_smoke_overlay.py [csv_path]
"""
import os, sys, csv, re, io
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
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


def parse_installs():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rdr = csv.reader(f); next(rdr)
        for i, r in enumerate(rdr):
            if not r or not r[0].strip():
                continue
            parts = [p.strip() for p in (r[1] or "").split(",")]
            if len(parts) < 3:
                continue
            zc = re.search(r"\b(\d{5})\b", r[1]); zc = zc.group(1) if zc else ""
            rows.append({"id": str(i), "street": parts[0], "city": parts[1] if len(parts) > 1 else "BATON ROUGE",
                         "state": "LA", "zip": zc, "status": (r[7] or "").strip()})
    return rows


def geocode(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
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


def main():
    installs = parse_installs()
    print(f"installs parsed: {len(installs)}", file=sys.stderr)
    coords = geocode(installs)
    print(f"geocoded: {len(coords)} ({len(coords)/len(installs)*100:.0f}%)", file=sys.stderr)

    gj = brla.get_geojson("q7v5-ijjg")
    tracts = []
    for f in gj["features"]:
        p = f["properties"]
        tracts.append({"geom": shape(f["geometry"]), "fips": p.get("fips"),
                       "svi": num(p.get("rpl_themes")),
                       "pct_pov": round((num(p.get("ep_pov")) or 0) * 100)})
        # add display % for tooltip
        f["properties"]["pct_pov"] = round((num(p.get("ep_pov")) or 0) * 100)
        f["properties"]["completed"] = 0

    # assign completed installs to tracts (point-in-polygon)
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
                    t.setdefault("done_n", 0); t["done_n"] += 1
                break
        if done:
            completed_pts.append(c)
    for f in gj["features"]:
        fp = f["properties"].get("fips")
        f["properties"]["completed"] = by_fips.get(fp, {}).get("done_n", 0)

    # gap: high SVI + few completed installs
    ranked = sorted((t for t in tracts if t["svi"] is not None), key=lambda t: t["svi"], reverse=True)
    print(f"\n=== TARGET GAP: most-vulnerable tracts with FEWEST completed installs ===")
    print(f"{'Tract FIPS':<14}{'SVI':>6}{'%Pov':>6}{'Installs':>9}")
    print("-" * 36)
    targets = [t for t in ranked if t["svi"] >= 0.80]
    for t in sorted(targets, key=lambda t: (t.get("done_n", 0), -t["svi"]))[:12]:
        print(f"{t['fips']:<14}{t['svi']:>6.2f}{t['pct_pov']:>5}%{t.get('done_n', 0):>9}")
    zero = [t for t in targets if t.get("done_n", 0) == 0]
    print(f"\n{len(zero)} of {len(targets)} high-vulnerability tracts (SVI>=0.80) have ZERO completed installs.")

    # --- map ---
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
    fg.add_to(m)
    cmap.add_to(m); folium.LayerControl().add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<h3 style='font-family:sans-serif'>Smoke-Alarm Coverage vs. Social Vulnerability</h3>"
        "<p style='font-family:sans-serif;color:#555'>Dark tracts = high vulnerability. Blue dots = "
        "completed installs. <b>Dark areas with no dots = priority CRR canvassing targets.</b></p>"))
    out = os.path.join(OUT, "BRFD_SVI_SmokeAlarm_Overlay.html")
    m.save(out)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
