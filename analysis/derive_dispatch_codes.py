"""
Utility: derive what each BRFD dispatch_type_code means, from the data itself.

For a sample of incidents, cross-references each dispatch_type_code against the
dominant NFIRS actual_incident_type it maps to. Use this to refresh the LAB dict
in dispatch_center_report.py if codes change.

Usage:  python derive_dispatch_codes.py [START yyyy-mm-dd] [END yyyy-mm-dd]
"""
import os, sys, json
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)
from firstdue_mcp.client import FirstDueClient

START = sys.argv[1] if len(sys.argv) > 1 else "2026-05-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-07-09"

NFIRS = {"111": "Building fire", "321": "EMS call / transport", "322": "MVA w/ injuries",
         "412": "Gas leak", "553": "Public service", "600": "Good intent",
         "700": "False alarm", "745": "Alarm activation no fire"}


def main():
    c = FirstDueClient(timeout=120)
    rows, page = [], 1
    while page <= 20:
        env = c.request("GET", "/fire-incidents",
                        params={"start_alarm_at": f"{START}T00:00:00Z", "end_alarm_at": f"{END}T00:00:00Z", "page": page})
        b = env.get("fire_incidents", [])
        if not b: break
        rows.extend(b)
        if page >= env.get("pages", page): break
        page += 1
    print(f"sample: {len(rows)} incidents ({START}..{END})\n")
    by_code = defaultdict(Counter)
    for inc in rows:
        by_code[(inc.get("dispatch_type_code") or "—").strip()][(inc.get("actual_incident_type") or "").strip()] += 1
    for code, types in sorted(by_code.items(), key=lambda x: -sum(x[1].values())):
        top = types.most_common(2)
        desc = ", ".join(f"{t or '?'} {NFIRS.get(t, '')} ({n})" for t, n in top)
        print(f"{code:<6} n={sum(types.values()):<6} -> {desc}")


if __name__ == "__main__":
    main()
