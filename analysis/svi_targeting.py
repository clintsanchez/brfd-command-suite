"""
Community-risk targeting via CDC/ATSDR Social Vulnerability Index (SVI).

Pulls the 2022 SVI (census-tract) for East Baton Rouge Parish, saves it as a committed
reference (reference/svi_ebr_tracts.csv), and ranks the most socially-vulnerable tracts —
a validated, multi-factor upgrade to elderly-only CRR targeting (smoke_alarm_gap.py).

SVI overall ranking = RPL_THEMES (0-1 percentile vs. all US tracts; higher = more vulnerable).
Themes: 1 socioeconomic, 2 household characteristics (age/disability), 3 racial/ethnic minority,
4 housing type / transportation. Value -999 = suppressed/missing.

Source: https://www.atsdr.cdc.gov/place-health/php/svi/  (public domain)
Usage:  python svi_targeting.py
"""
import os, sys, csv, io
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(ROOT, "reference")

STATE_URL = "https://svi.cdc.gov/Documents/Data/2022/csv/states/Louisiana.csv"
EBR_STCNTY = "22033"
KEEP = ["FIPS", "LOCATION", "E_TOTPOP", "RPL_THEMES",
        "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4",
        "EP_AGE65", "EP_DISABL", "EP_POV150", "EP_MINRTY"]


def main():
    print("fetching CDC/ATSDR 2022 SVI (Louisiana)...", file=sys.stderr)
    r = requests.get(STATE_URL, timeout=90); r.raise_for_status()
    rows = [row for row in csv.DictReader(io.StringIO(r.text)) if row.get("STCNTY") == EBR_STCNTY]
    print(f"  {len(rows)} East Baton Rouge tracts", file=sys.stderr)

    # save committed reference (trimmed columns)
    os.makedirs(REF, exist_ok=True)
    out_csv = os.path.join(REF, "svi_ebr_tracts.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEEP); w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in KEEP})
    print(f"saved -> reference/svi_ebr_tracts.csv", file=sys.stderr)

    def num(x):
        try:
            v = float(x)
            return None if v == -999 else v
        except (TypeError, ValueError):
            return None

    ranked = [r for r in rows if num(r.get("RPL_THEMES")) is not None]
    ranked.sort(key=lambda r: num(r["RPL_THEMES"]), reverse=True)

    print(f"\n=== Most socially-vulnerable EBR tracts (2022 SVI) — top 15 of {len(ranked)} ===")
    print(f"{'Tract (FIPS)':<13}{'Pop':>7}{'SVI':>6}{'%65+':>6}{'%Disab':>7}{'%Pov':>6}  Location")
    print("-" * 88)
    for r in ranked[:15]:
        loc = (r.get("LOCATION") or "").replace("Census Tract ", "CT ")[:34]
        print(f"{r['FIPS']:<13}{int(float(r['E_TOTPOP'])):>7,}{num(r['RPL_THEMES']):>6.2f}"
              f"{num(r.get('EP_AGE65')) or 0:>6.0f}{num(r.get('EP_DISABL')) or 0:>7.0f}"
              f"{num(r.get('EP_POV150')) or 0:>6.0f}  {loc}")
    hi = [r for r in ranked if num(r["RPL_THEMES"]) >= 0.90]
    print(f"\n{len(hi)} tracts are in the top 10% most-vulnerable nationally (SVI >= 0.90) — "
          f"prime CRR / smoke-alarm canvassing targets.")
    print("Combine with smoke_alarm_gap.py (ZIP-level installs) to find high-SVI areas with low coverage.")


if __name__ == "__main__":
    main()
