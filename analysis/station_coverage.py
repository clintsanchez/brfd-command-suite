"""
BRFD station drive-time coverage analysis.

Builds NFPA-1710 travel-time isochrones (4-min and 8-min) around each BRFD fire station
from the real OpenStreetMap street network, unions them into coverage areas, then overlays
actual First Due incidents to measure what share of demand falls inside vs. outside coverage.
Renders an interactive map to analysis/output/BRFD_Station_Coverage.html.

Station coordinates come from Baton Rouge open data (data.brla.gov) since First Due's
/stations endpoint returns names only. Isochrones use per-station convex hulls of the
reachable street network — a standard but slightly *optimistic* approximation (real coverage
is a bit less), so treat the gap findings as conservative.

Usage:  python station_coverage.py
"""
import os, sys, csv, io, re
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)

import requests
import networkx as nx
import osmnx as ox
import folium
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from firstdue_mcp.client import FirstDueClient

# OpenStreetMap data comes from an Overpass server. The default (overpass-api.de) is
# intermittently unreachable from some networks; set OVERPASS_URL to a mirror if needed,
# e.g. OVERPASS_URL=https://maps.mail.ru/osm/tools/overpass/api
ox.settings.requests_timeout = 300
if os.environ.get("OVERPASS_URL"):
    ox.settings.overpass_url = os.environ["OVERPASS_URL"]


def _union(geoms):
    gs = gpd.GeoSeries(list(geoms))
    return gs.union_all() if hasattr(gs, "union_all") else gs.unary_union

BANDS = [(240, "4 min", "#1a9850"), (480, "8 min", "#fdae61")]  # NFPA 1710 travel benchmarks
STATIONS_CSV = "https://data.brla.gov/api/views/h667-2xhn/rows.csv?accessType=DOWNLOAD"


def _speeds(G):
    add_sp = getattr(getattr(ox, "routing", ox), "add_edge_speeds", None) or ox.add_edge_speeds
    add_tt = getattr(getattr(ox, "routing", ox), "add_edge_travel_times", None) or ox.add_edge_travel_times
    return add_tt(add_sp(G))


def load_stations():
    r = requests.get(STATIONS_CSV, timeout=60); r.raise_for_status()
    out = []
    for row in csv.DictReader(io.StringIO(r.text)):
        if "BATON ROUGE FIRE" not in (row.get("AGENCY") or "").upper():
            continue
        m = re.search(r"POINT \(([-\d.]+) ([-\d.]+)\)", row.get("GEOMETRY") or "")
        if not m:
            continue
        out.append({"name": row.get("DESCRIPTION", "").strip(),
                    "lon": float(m.group(1)), "lat": float(m.group(2))})
    return out


def iso_from_center(Gp, center):
    """Return {seconds: polygon(4326)} for one station's center node — realistic reachable-
    street footprint (buffer the reachable edges by 30 m in the projected CRS, then union)."""
    polys = {}
    for secs, _, _ in BANDS:
        sub = nx.ego_graph(Gp, center, radius=secs, distance="travel_time")
        if sub.number_of_edges() == 0:
            continue
        edges = ox.graph_to_gdfs(sub, nodes=False)
        buffered = edges.geometry.buffer(30)
        merged = buffered.union_all() if hasattr(buffered, "union_all") else buffered.unary_union
        polys[secs] = gpd.GeoSeries([merged], crs=edges.crs).to_crs(4326).iloc[0]
    return polys


def pull_incident_points(c, n_pages=2):
    pts = []
    for pg in range(1, n_pages + 1):
        env = c.request("GET", "/fire-incidents",
                        params={"start_alarm_at": "2026-06-01T00:00:00Z",
                                "end_alarm_at": "2026-07-09T00:00:00Z", "page": pg})
        for inc in env.get("fire_incidents", []):
            try:
                lat, lon = float(inc["latitude"]), float(inc["longitude"])
                if 29 < lat < 31 and -92 < lon < -90:
                    pts.append((lon, lat))
            except (TypeError, ValueError, KeyError):
                pass
    return pts


def main():
    print("loading stations...", file=sys.stderr)
    stations = load_stations()
    print(f"  {len(stations)} BRFD stations", file=sys.stderr)

    # ONE street-network download for the whole station extent (avoids Overpass rate limits),
    # projected once; then compute every station's isochrones from that single graph.
    lats = [s["lat"] for s in stations]; lons = [s["lon"] for s in stations]
    mgn = 0.045
    bbox = (min(lons) - mgn, min(lats) - mgn, max(lons) + mgn, max(lats) + mgn)  # (W,S,E,N)
    print("downloading street network (single Overpass query)...", file=sys.stderr)
    G = _speeds(ox.graph_from_bbox(bbox, network_type="drive"))
    print(f"  network: {G.number_of_nodes():,} nodes; projecting...", file=sys.stderr)
    Gp = ox.project_graph(G)
    centers = ox.distance.nearest_nodes(G, X=lons, Y=lats)

    band_polys = {secs: [] for secs, _, _ in BANDS}
    for i, (st, center) in enumerate(zip(stations, centers), 1):
        print(f"isochrones {i}/{len(stations)}: {st['name']}", file=sys.stderr)
        for secs, poly in iso_from_center(Gp, center).items():
            band_polys[secs].append(poly)

    coverage = {secs: unary_union(polys) for secs, polys in band_polys.items() if polys}

    print("pulling incidents...", file=sys.stderr)
    c = FirstDueClient(timeout=90)
    incs = pull_incident_points(c)
    inside = {secs: 0 for secs in coverage}
    uncovered = []
    for lon, lat in incs:
        p = Point(lon, lat)
        covered_any = False
        for secs in sorted(coverage):
            if coverage[secs].contains(p):
                inside[secs] += 1; covered_any = True; break
        if not covered_any:
            uncovered.append((lon, lat))
    total = len(incs) or 1

    print("\n=== BRFD station drive-time coverage ===")
    print(f"stations: {len(stations)} | incidents sampled: {len(incs)}")
    cum = 0
    for secs, lbl, _ in BANDS:
        if secs in inside:
            cum += inside[secs]
            print(f"  within {lbl} drive: {cum:>5} incidents ({cum/total*100:.0f}%)")
    print(f"  OUTSIDE 8-min:     {len(uncovered):>5} incidents ({len(uncovered)/total*100:.0f}%)  <- coverage gaps")

    # --- map ---
    clat = median(s["lat"] for s in stations); clon = median(s["lon"] for s in stations)
    m = folium.Map(location=[clat, clon], zoom_start=12, tiles="cartodbpositron")
    for secs, lbl, color in reversed(BANDS):  # 8-min under 4-min
        if secs in coverage:
            folium.GeoJson(coverage[secs].__geo_interface__,
                           style_function=lambda _f, c=color: {"fillColor": c, "color": c,
                                                               "weight": 1, "fillOpacity": 0.25},
                           name=f"{lbl} coverage").add_to(m)
    for lon, lat in uncovered:
        folium.CircleMarker([lat, lon], radius=2, color="#d73027", fill=True,
                            fill_opacity=0.7, weight=0).add_to(m)
    for st in stations:
        folium.Marker([st["lat"], st["lon"]], tooltip=st["name"],
                      icon=folium.Icon(color="blue", icon="fire", prefix="fa")).add_to(m)
    folium.LayerControl().add_to(m)
    title = ("<h3 style='font-family:sans-serif'>BRFD Station Drive-Time Coverage</h3>"
             "<p style='font-family:sans-serif;color:#555'>Green = 4-min, orange = 8-min NFPA travel "
             "isochrones. Red dots = incidents outside 8-min coverage (gaps). Approximate (optimistic).</p>")
    m.get_root().html.add_child(folium.Element(title))
    out = os.path.join(OUT, "BRFD_Station_Coverage.html")
    m.save(out)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
