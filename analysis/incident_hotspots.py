"""
BRFD incident hotspot map (H3 hex-grid density).

Pulls First Due incidents for a date range, bins them into Uber H3 hexagons, and renders
an interactive choropleth of call density to analysis/output/BRFD_Incident_Hotspots.html.
Also prints the top hotspot hexes (with the dominant incident type via the NFIRS reference).

Usage:  python incident_hotspots.py [START yyyy-mm-dd] [END yyyy-mm-dd] [H3_RES]
"""
import os, sys
from collections import Counter, defaultdict
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)

import h3
import folium
import branca.colormap as cm
from firstdue_mcp.client import FirstDueClient
from reference.nfirs import label, category

START = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-07-09"
RES = int(sys.argv[3]) if len(sys.argv) > 3 else 8   # ~0.7 km^2 hexes


def pull(c):
    rows, page = [], 1
    while page <= 40:
        env = c.request("GET", "/fire-incidents",
                        params={"start_alarm_at": f"{START}T00:00:00Z",
                                "end_alarm_at": f"{END}T00:00:00Z", "page": page})
        b = env.get("fire_incidents", [])
        if not b:
            break
        rows.extend(b)
        if page >= env.get("pages", page):
            break
        page += 1
    return rows


def main():
    c = FirstDueClient(timeout=90)
    print(f"pulling incidents {START}..{END}...", file=sys.stderr)
    rows = pull(c)

    cell_count = Counter()
    cell_types = defaultdict(Counter)
    used = 0
    for inc in rows:
        try:
            lat, lon = float(inc["latitude"]), float(inc["longitude"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (29 < lat < 31 and -92 < lon < -90):
            continue
        cell = h3.latlng_to_cell(lat, lon, RES)
        cell_count[cell] += 1
        cell_types[cell][(inc.get("actual_incident_type") or "").strip()] += 1
        used += 1

    print(f"incidents mapped: {used} | hexes: {len(cell_count)} (res {RES})")
    print("\nTop 10 hotspot hexes:")
    for cell, n in cell_count.most_common(10):
        top_type = cell_types[cell].most_common(1)[0][0]
        lat, lon = h3.cell_to_latlng(cell)
        print(f"  {n:>4} calls @ ({lat:.4f},{lon:.4f})  top: {top_type} {label(top_type)}")

    # --- map ---
    counts = sorted(cell_count.values())
    vmax = counts[int(len(counts) * 0.97)] if counts else 1   # cap at 97th pct so a few huge cells don't wash out
    colormap = cm.linear.YlOrRd_09.scale(1, max(vmax, 2))
    colormap.caption = f"Incidents per hex ({START}..{END})"

    lat0 = median(h3.cell_to_latlng(cl)[0] for cl in cell_count)
    lon0 = median(h3.cell_to_latlng(cl)[1] for cl in cell_count)
    m = folium.Map(location=[lat0, lon0], zoom_start=12, tiles="cartodbpositron")
    for cell, n in cell_count.items():
        boundary = [[la, lo] for la, lo in h3.cell_to_boundary(cell)]
        top = cell_types[cell].most_common(1)[0][0]
        folium.Polygon(
            boundary, color=None, weight=0, fill=True,
            fill_color=colormap(min(n, vmax)), fill_opacity=0.6,
            tooltip=f"{n} calls · top: {label(top)}",
        ).add_to(m)
    colormap.add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<h3 style='font-family:sans-serif'>BRFD Incident Hotspots</h3>"
        f"<p style='font-family:sans-serif;color:#555'>Call density by H3 hex, {used:,} incidents "
        f"{START} to {END}. Darker = more calls.</p>"))
    out = os.path.join(OUT, "BRFD_Incident_Hotspots.html")
    m.save(out)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
