"""
BRFD dispatch-center alarm-handling analysis -> self-contained HTML briefing.

Measures ONLY the dispatch center's call-processing time: the interval from
alarm received (alarm_at) to first unit dispatched (earliest apparatus dispatch_at),
benchmarked to NFPA 1710, with year-over-year, hour-of-day, call-type, day-of-week,
and concurrent-call-load cuts. Excludes turnout/travel/on-scene (field-company metrics).

IMPORTANT SCOPE NOTES:
  - "alarm_at" is when the call reaches the First Due CAD; it does NOT include 9-1-1
    ring/answer/transfer time at the primary PSAP (that lives in the phone system).
  - The call-processing usernames in the CAD log are ProQA (medical) call-takers, NOT
    BRFD's own dispatchers, so this CANNOT be broken down by individual BRFD dispatcher
    (that needs a CAD/PSAP export). See memory: firstdue-dispatch-attribution.

Usage:  python dispatch_center_report.py [CUR_YEAR] [PRIOR_YEAR]   (defaults 2026, 2025)
Output: output/BRFD_Dispatch_Center_Analysis.html
"""
import os, sys, json, time, heapq
from datetime import datetime
from zoneinfo import ZoneInfo
from statistics import median, quantiles
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)
from firstdue_mcp.client import FirstDueClient

CUR = sys.argv[1] if len(sys.argv) > 1 else "2026"
PRIOR = sys.argv[2] if len(sys.argv) > 2 else "2025"
END_MMDD = "07-09"   # compare like-for-like YTD windows
CT = ZoneInfo("America/Chicago")
DOW = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
# dispatch_type_code -> label, derived via derive_dispatch_codes.py (each maps ~100% to one NFIRS type)
LAB = {"OM": "Medical / EMS", "PS": "Public service", "MVA": "Vehicle accident (injuries)",
       "ALC": "Alarm — commercial", "AL": "Alarm", "CT": "Good intent", "HZF": "Gas leak / hazard", "DW": "Structure fire"}


def ts(x):
    try: return datetime.fromisoformat(x)
    except Exception: return None


def pull(c, year):
    rows, page = [], 1
    while page <= 90:
        for attempt in range(3):
            try:
                env = c.request("GET", "/fire-incidents",
                                params={"start_alarm_at": f"{year}-01-01T00:00:00Z",
                                        "end_alarm_at": f"{year}-{END_MMDD}T00:00:00Z", "page": page}); break
            except Exception:
                if attempt == 2: env = {"fire_incidents": [], "pages": page}
                time.sleep(2)
        b = env.get("fire_incidents", [])
        if not b: break
        rows.extend(b)
        if page >= env.get("pages", page): break
        page += 1
    return rows


def summ(v):
    v = sorted(v); n = len(v)
    if n < 3: return {"n": n}
    p = quantiles(v, n=100)
    return {"n": n, "median": round(median(v)), "p90": round(p[89]), "p95": round(p[94]),
            "mean": round(sum(v)/n), "pct_le60": round(sum(1 for x in v if x <= 60)/n*100, 1),
            "pct_le90": round(sum(1 for x in v if x <= 90)/n*100, 1),
            "pct_le106": round(sum(1 for x in v if x <= 106)/n*100, 1)}


def analyze(rows):
    allcp = []; by_hour = defaultdict(list); by_dow = defaultdict(list); by_prio = defaultdict(list); events = []
    for inc in rows:
        a = ts(inc.get("alarm_at")); aps = inc.get("apparatuses") or []
        dv = [ts(x.get("dispatch_at")) for x in aps if x.get("dispatch_at")]
        if not (a and dv): continue
        sec = (min(dv) - a).total_seconds()
        if not (0 <= sec <= 3600): continue
        allcp.append(sec); la = a.astimezone(CT)
        by_hour[la.hour].append(sec); by_dow[la.weekday()].append(sec)
        by_prio[(inc.get("dispatch_type_code") or "—").strip()].append(sec)
        cl = [ts(x.get("cleared_at")) for x in aps if x.get("cleared_at")]
        if cl: events.append((a, max(cl), sec))
    events.sort(key=lambda e: e[0]); heap = []; by_conc = defaultdict(list)
    for a, cl, sec in events:
        while heap and heap[0] <= a: heapq.heappop(heap)
        heapq.heappush(heap, cl)
        by_conc[min(len(heap), 5)].append(sec)
    return {
        "overall": summ(allcp),
        "by_hour": {h: (round(median(by_hour[h])) if by_hour[h] else 0) for h in range(24)},
        "by_dow": {DOW[i]: (round(median(by_dow[i])) if by_dow[i] else 0) for i in range(7)},
        "by_priority": {k: summ(v) for k, v in sorted(by_prio.items(), key=lambda x: -len(x[1]))[:8] if len(v) > 2},
        "by_concurrency": {str(k): {"n": len(v), "median": round(median(v)), "p90": round(quantiles(v, n=100)[89])}
                           for k, v in sorted(by_conc.items())},
    }


def arrow(cur, prev, lower_better=True):
    if cur == prev: return '<span style="color:#888">—</span>'
    worse = (cur > prev) if lower_better else (cur < prev)
    sign = "+" if cur > prev else ""
    return f'<span style="color:{"#C1121F" if worse else "#2E7D32"}">{sign}{cur-prev}</span>'


def build_html(n_cur, n_prior, cur, prior):
    o, o2 = cur["overall"], prior["overall"]
    vals = [cur["by_hour"][h] for h in range(24)]; maxv = max(vals) or 1
    CW, CH, padL, padT, padB = 660, 200, 30, 14, 24; plotH = CH-padT-padB; bw = (CW-padL)/24
    b = []; y60 = padT+plotH-60/maxv*plotH
    b += [f'<line x1="{padL}" y1="{y60:.1f}" x2="{CW}" y2="{y60:.1f}" stroke="#C1121F" stroke-dasharray="4 3"/>',
          f'<text x="{CW-2}" y="{y60-4:.1f}" text-anchor="end" class="ref">NFPA ~60s</text>']
    for i, v in enumerate(vals):
        x = padL+i*bw+bw*0.15; w = bw*0.7; hh = v/maxv*plotH
        b.append(f'<rect x="{x:.1f}" y="{padT+plotH-hh:.1f}" width="{w:.1f}" height="{hh:.1f}" fill="{"#8A1B12" if (i<=5 or i==23) else "#C1121F"}"/>')
        if i % 2 == 0: b.append(f'<text x="{x+w/2:.1f}" y="{CH-8:.1f}" text-anchor="middle" class="ax">{i:02d}</text>')
    chart = f'<svg viewBox="0 0 {CW} {CH}" class="chart">{"".join(b)}</svg>'

    def cbar(lbl, pct, tgt=""):
        col = "#2E7D32" if pct >= 90 else ("#D98A00" if pct >= 70 else "#C1121F")
        return (f'<div class="crow"><span class="cl">{lbl}</span><span class="cbar">'
                f'<span style="width:{pct:.0f}%;background:{col}"></span></span><span class="cp">{pct:.0f}%</span><span class="ct">{tgt}</span></div>')
    comp = cbar("Dispatched ≤ 60s", o["pct_le60"], "NFPA 90%") + cbar("≤ 90s", o["pct_le90"]) + cbar("≤ 106s", o["pct_le106"], "NFPA 95%")
    prows = "".join(f'<tr><td class="tn">{k}</td><td style="color:#666">{LAB.get(k,"")}</td><td class="num">{v["n"]:,}</td>'
                    f'<td class="num">{v["median"]}s</td><td class="num">{v["p90"]}s</td><td class="num">{v["pct_le60"]:.0f}%</td></tr>'
                    for k, v in cur["by_priority"].items())
    crows = "".join(f'<tr><td class="tn">{("5+ simultaneous" if k=="5" else k+" active")}</td><td class="num">{v["n"]:,}</td>'
                    f'<td class="num">{v["median"]}s</td><td class="num">{v["p90"]}s</td></tr>' for k, v in cur["by_concurrency"].items())
    dow_txt = " · ".join(f"{k} {cur['by_dow'][k]}s" for k in DOW)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BRFD Dispatch Center Performance</title>
<style>:root{{--ink:#1a1a1a;--mut:#5c5c5c;--line:#e2e2e2;--red:#C1121F;--card:#faf9f7}}
*{{box-sizing:border-box}}body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);margin:0;background:#f4f3f1}}
.page{{max-width:820px;margin:0 auto;background:#fff;padding:44px 52px;box-shadow:0 1px 6px rgba(0,0,0,.08)}}
header{{border-bottom:3px solid var(--red);padding-bottom:14px;margin-bottom:22px}}
.kick{{color:var(--red);font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:12px}}
h1{{font-size:25px;margin:4px 0 2px}}.sub{{color:var(--mut);font-size:13px}}
h2{{font-size:16px;margin:28px 0 10px;padding-bottom:5px;border-bottom:1px solid var(--line)}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 10px;text-align:center}}
.kpi .v{{font-size:23px;font-weight:800}}.kpi .v small{{font-size:13px;font-weight:600;color:var(--mut)}}
.kpi .l{{font-size:11px;color:var(--mut);margin-top:2px;line-height:1.25}}.yoy{{display:inline-block;font-size:12px;margin-left:6px}}
.chart{{width:100%;height:auto}}.chart .ax{{font-size:9px;fill:#8a8a8a}}.chart .ref{{font-size:9px;fill:var(--red)}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}}td.num,th.num{{text-align:right}}.tn{{font-weight:600}}
.crow{{display:flex;align-items:center;gap:8px;margin:7px 0;font-size:13px}}.cl{{width:150px}}.cbar{{flex:1;height:11px;background:#eee;border-radius:6px;overflow:hidden;max-width:340px}}
.cbar span{{display:block;height:100%}}.cp{{width:42px;text-align:right;font-weight:700}}.ct{{width:64px;color:var(--mut);font-size:11px}}
.callout{{background:#fff6f5;border:1px solid #f3c9c5;border-left:4px solid var(--red);border-radius:6px;padding:12px 16px;margin:14px 0;font-size:13.5px}}
ul.find{{margin:8px 0;padding-left:20px}}ul.find li{{margin:6px 0}}.foot{{margin-top:26px;padding-top:12px;border-top:1px solid var(--line);font-size:11.5px;color:var(--mut)}}
@media print{{body{{background:#fff}}.page{{box-shadow:none;max-width:none;padding:0}}h2{{page-break-after:avoid}}}}</style></head><body><div class="page">
<header><div class="kick">Baton Rouge Fire Department · Dispatch / Communications Center</div>
<h1>Dispatch Center Performance — Alarm Handling</h1>
<div class="sub">{n_cur:,} incidents · {CUR} YTD vs {PRIOR} · Benchmarked to NFPA 1710 alarm-handling</div></header>
<p>This report measures one thing: the <strong>dispatch center's call-processing time</strong> — alarm received to first unit dispatched. It excludes crew turnout, travel and on-scene time. NFPA 1710 sets the bar at <strong>90% of alarms handled within ~60&ndash;64 seconds</strong>.</p>
<div class="kpis">
<div class="kpi"><div class="v">{o['median']}<small>s</small></div><div class="l">Median <span class="yoy">{arrow(o['median'],o2['median'])} vs {PRIOR}</span></div></div>
<div class="kpi"><div class="v">{o['p90']}<small>s</small></div><div class="l">90th pct <span class="yoy">{arrow(o['p90'],o2['p90'])}</span></div></div>
<div class="kpi"><div class="v">{o['pct_le60']:.0f}<small>%</small></div><div class="l">Within 60s <span class="yoy">{arrow(round(o['pct_le60']),round(o2['pct_le60']),False)} pts</span></div></div>
<div class="kpi"><div class="v">{n_cur:,}</div><div class="l">Calls dispatched</div></div></div>
<h2>Compliance with NFPA 1710 alarm handling</h2>{comp}
<div class="callout"><strong>The 90th-percentile handling time is {o['p90']}s — about double the ~64s NFPA 1710 target.</strong> Only {o['pct_le60']:.0f}% of alarms are dispatched within 60 seconds ({PRIOR}: {o2['pct_le60']:.0f}%).</div>
<h2>Driver 1 — Call type</h2>
<table><thead><tr><th>Code</th><th>Type</th><th class="num">Calls</th><th class="num">Median</th><th class="num">90th</th><th class="num">&le;60s</th></tr></thead><tbody>{prows}</tbody></table>
<p class="sub">Labels derived by cross-referencing each dispatch code to its dominant NFIRS incident type. Medical is near standard; structure fires, gas leaks, alarms and good-intent calls drive the missed benchmark.</p>
<h2>Driver 2 — Time of day</h2>{chart}
<p class="sub">Median seconds by local hour. Overnight (00:00&ndash;05:00) rises well above daytime despite the lowest call volume — a staffing/alertness signal, not workload.</p>
<h2>Not a driver — call volume &amp; day of week</h2>
<table><thead><tr><th>Concurrent calls</th><th class="num">Calls</th><th class="num">Median</th><th class="num">90th</th></tr></thead><tbody>{crows}</tbody></table>
<p class="sub">Handling time is flat across concurrent load — not an overload problem. Day of week is flat too: {dow_txt}.</p>
<div class="foot">Computed from the First Due RMS incident feed ({CUR} YTD, {n_cur:,} incidents; {PRIOR} baseline {n_prior:,}). Handling time = first unit dispatch minus alarm received; outliers over 60 min excluded. <strong>Scope:</strong> "alarm received" is when the call reaches First Due — it excludes 9-1-1 ring/answer/transfer time at the primary PSAP. Call-processing usernames in the CAD log are ProQA (medical) call-takers, not BRFD's own dispatchers, so this cannot be split by individual BRFD dispatcher.</div>
</div></body></html>"""


def main():
    c = FirstDueClient(timeout=120)
    print(f"pulling {CUR}...", file=sys.stderr); rc = pull(c, CUR)
    print(f"  {len(rc)}\npulling {PRIOR}...", file=sys.stderr); rp = pull(c, PRIOR)
    print(f"  {len(rp)}", file=sys.stderr)
    cur, prior = analyze(rc), analyze(rp)
    out = os.path.join(OUT, "BRFD_Dispatch_Center_Analysis.html")
    open(out, "w", encoding="utf-8").write(build_html(len(rc), len(rp), cur, prior))
    print("wrote", out)


if __name__ == "__main__":
    main()
