"""
Social Vulnerability Index choropleth map for East Baton Rouge.

Pulls the SVI census-tract layer (with geometry) straight from data.brla.gov and renders an
interactive choropleth colored by overall vulnerability (RPL_THEMES) — the visual companion
to svi_targeting.py's ranked table, for CRR / smoke-alarm canvassing.

Source: data.brla.gov dataset q7v5-ijjg (2018 SVI, EBR tracts). Usage: python svi_map.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, HERE)   # for brla

import folium
import branca.colormap as cm
import brla


def num(x):
    try:
        v = float(x)
        return None if v == -999 else v
    except (TypeError, ValueError):
        return None


def main():
    print("fetching SVI tracts (geometry) from data.brla.gov...", file=sys.stderr)
    gj = brla.get_geojson("q7v5-ijjg")
    feats = gj["features"]
    print(f"  {len(feats)} tracts", file=sys.stderr)

    # ep_* fields are proportions (0-1); add rounded-percent fields for display
    for f in feats:
        p = f["properties"]
        for src, dst in (("ep_age65", "pct_65"), ("ep_disabl", "pct_disab"), ("ep_pov", "pct_pov")):
            v = num(p.get(src))
            p[dst] = round(v * 100) if v is not None else None

    cmap = cm.linear.YlOrRd_09.scale(0, 1)
    cmap.caption = "Social Vulnerability Index (RPL_THEMES) — higher = more vulnerable"

    def style(feat):
        v = num(feat["properties"].get("rpl_themes"))
        return {"fillColor": cmap(v) if v is not None else "#cccccc",
                "color": "#555", "weight": 0.4, "fillOpacity": 0.72}

    m = folium.Map(location=[30.45, -91.13], zoom_start=11, tiles="cartodbpositron")
    folium.GeoJson(
        gj, name="SVI", style_function=style,
        highlight_function=lambda _f: {"weight": 2, "color": "#000"},
        tooltip=folium.GeoJsonTooltip(
            fields=["fips", "rpl_themes", "pct_65", "pct_disab", "pct_pov", "e_totpop"],
            aliases=["Tract FIPS", "SVI (0-1)", "% age 65+", "% disabled", "% poverty", "Population"],
            localize=True),
    ).add_to(m)
    cmap.add_to(m)
    m.get_root().html.add_child(folium.Element(
        "<h3 style='font-family:sans-serif'>East Baton Rouge — Social Vulnerability Index</h3>"
        "<p style='font-family:sans-serif;color:#555'>Darker tracts = more socially vulnerable "
        "(CDC/ATSDR SVI via data.brla.gov). Prime CRR / smoke-alarm canvassing areas.</p>"))
    out = os.path.join(OUT, "BRFD_SVI_Map.html")
    m.save(out)

    ranked = sorted((f["properties"] for f in feats if num(f["properties"].get("rpl_themes")) is not None),
                    key=lambda p: num(p["rpl_themes"]), reverse=True)
    print(f"\nMost vulnerable tracts (top 8 of {len(ranked)}):")
    for p in ranked[:8]:
        print(f"  {p['fips']}  SVI {num(p['rpl_themes']):.2f}  | 65+ {p.get('pct_65') or 0}%  "
              f"disab {p.get('pct_disab') or 0}%  pov {p.get('pct_pov') or 0}%")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
