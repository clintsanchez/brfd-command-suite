"""
Smoke-alarm coverage vs. senior-population gap analysis, by ZIP.

Cross-references BRFD Community Connect smoke-alarm requests (exported from the
First Due UI as CSV) against Census senior population (ACS via Census Reporter,
keyless) to rank neglected areas: high 65+ population, low install coverage.

Inputs:
  - Community Connect export CSV. Default path below; override with argv[1].
    Expected columns include ADDRESS (with ZIP) and STATUS.
Output:
  - output/smoke_alarm_gap.json  (ZIP-aggregate; no PII)

Note: the input CSV contains resident PII — it is read locally only and never
committed (see .gitignore). All output is ZIP-level aggregate.
"""
import os, sys, csv, re, json, requests
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\csanchez\Downloads\Smoke Alarm Request Report.csv"

# East Baton Rouge Parish / Baton Rouge-area residential ZCTAs
BR_CORE = ["70801","70802","70805","70806","70807","70808","70809","70810","70811",
           "70812","70814","70815","70816","70817","70818","70819","70820",
           "70714","70791","70739","70770","70803","70813"]


def main():
    # 1. parse CSV -> per-ZIP request/status tallies
    by_zip = defaultdict(Counter); statuses = Counter(); total = 0
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rdr = csv.reader(f); next(rdr)
        for row in rdr:
            if not row or not row[0].strip():
                continue
            total += 1
            status = (row[7] or "").strip(); statuses[status] += 1
            m = re.search(r"\b(70\d{3})\b", row[1])
            if not m:
                continue
            z = m.group(1)
            by_zip[z]["requests"] += 1; by_zip[z][status] += 1
    print(f"parsed {total} requests | statuses: {dict(statuses)} | ZIPs: {len(by_zip)}")

    # 2. senior population per ZIP (Census Reporter, ACS 5yr, table B01001)
    zips = sorted(set(BR_CORE) | set(by_zip))
    geo = ",".join("86000US" + z for z in zips)
    r = requests.get("https://api.censusreporter.org/1.0/data/show/latest",
                     params={"table_ids": "B01001", "geo_ids": geo}, timeout=90)
    r.raise_for_status(); j = r.json()
    M65 = [f"B01001{n:03d}" for n in (20,21,22,23,24,25)]
    F65 = [f"B01001{n:03d}" for n in (44,45,46,47,48,49)]
    pop = {}
    for z in zips:
        est = j["data"].get("86000US" + z, {}).get("B01001", {}).get("estimate")
        if not est:
            continue
        tot = est.get("B01001001") or 0
        e65 = sum(est.get(v, 0) or 0 for v in M65 + F65)
        pop[z] = {"pop": int(tot), "e65": int(e65), "pct65": (e65/tot*100) if tot else 0}

    # 3. join + coverage metric (completed installs per 1,000 seniors)
    rows = []
    for z in zips:
        p = pop.get(z, {"pop": 0, "e65": 0, "pct65": 0}); c = by_zip.get(z, Counter())
        comp = c.get("Completed", 0); e65 = p["e65"]
        rows.append({"zip": z, "pop": p["pop"], "e65": e65, "pct65": round(p["pct65"], 1),
                     "requests": c.get("requests", 0), "completed": comp,
                     "cov_per_1k_senior": round((comp/e65*1000) if e65 else 0, 2)})

    print(f"\n{'ZIP':<7}{'Pop':>8}{'65+':>7}{'%65+':>7}{'Reqs':>6}{'Compl':>7}{'Inst/1k':>9}")
    print("-" * 51)
    for d in sorted(rows, key=lambda x: x["e65"], reverse=True):
        print(f"{d['zip']:<7}{d['pop']:>8,}{d['e65']:>7,}{d['pct65']:>6.1f}%"
              f"{d['requests']:>6}{d['completed']:>7}{d['cov_per_1k_senior']:>9.2f}")

    json.dump({"source_release": j.get("release", {}).get("name"), "rows": rows},
              open(os.path.join(OUT, "smoke_alarm_gap.json"), "w"), indent=2)
    print("\nsaved -> output/smoke_alarm_gap.json")


if __name__ == "__main__":
    main()
