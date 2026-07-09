"""
BRFD training program overview -> self-contained HTML briefing.

Pulls Training activities from the First Due event log for a date range,
computes program-overview metrics, and writes a shareable HTML report.

Data source: GET /event-log/activities?module=Training (cursor-paginated).
Session status is recorded at the session level (Complete/Incomplete) — there is
no per-person pass/fail and no training-hours field. fireStations/shifts are not
populated, so no per-station breakdown is possible.

Usage:  python training_report.py [START yyyy-mm-dd] [END yyyy-mm-dd]
Output: output/BRFD_Training_Analysis.html
"""
import os, sys, json, html
from collections import Counter
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "output"); os.makedirs(OUT, exist_ok=True)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".env"))
sys.path.insert(0, ROOT)
from firstdue_mcp.client import FirstDueClient

START = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-07-08"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def pull(c):
    sessions, cursor = [], None
    while True:
        params = {"module": "Training", "pageSize": 500, "date_from": START, "date_to": END}
        if cursor:
            params.update(cursor=cursor, direction="next")
        r = c.request("GET", "/event-log/activities", params=params)
        res = r.get("results", [])
        sessions.extend(res)
        cursor = r.get("next_cursor")
        if not cursor or not res:
            break
    return sessions


def names(s):
    return [x.strip() for x in (s.get("personnel") or "").split(";") if x.strip()]


def mkey(s):
    try:
        m, _, y = s["date"].split("/"); return f"{y}-{int(m):02d}"
    except Exception:
        return "?"


def build_html(k, monthly, topics):
    maxv = max((m["sessions"] for m in monthly), default=1) or 1
    CW, CH, padL, padB, padT = 620, 240, 34, 26, 10
    plotH = CH - padB - padT; barW = (CW - padL) / max(len(monthly), 1)
    bars = []
    for i, m in enumerate(monthly):
        x = padL + i*barW + barW*0.18; w = barW*0.64
        ch = m["complete"]/maxv*plotH; ih = m["incomplete"]/maxv*plotH
        yc = padT+plotH-ch; yi = yc-ih
        bars += [f'<rect x="{x:.1f}" y="{yc:.1f}" width="{w:.1f}" height="{ch:.1f}" fill="#2E7D32"/>',
                 f'<rect x="{x:.1f}" y="{yi:.1f}" width="{w:.1f}" height="{ih:.1f}" fill="#D98A00"/>',
                 f'<text x="{x+w/2:.1f}" y="{yi-4:.1f}" text-anchor="middle" class="bl">{m["sessions"]}</text>',
                 f'<text x="{x+w/2:.1f}" y="{CH-8:.1f}" text-anchor="middle" class="ax">{m["month"]}</text>']
    chart = f'<svg viewBox="0 0 {CW} {CH}" class="chart">{"".join(bars)}</svg>'
    trows = ""
    for t in topics:
        pct = t["complete_pct"]
        color = "#2E7D32" if pct >= 75 else ("#D98A00" if pct >= 40 else "#C1121F")
        trows += (f'<tr><td class="tn">{html.escape(t["topic"].title())}</td><td class="num">{t["sessions"]}</td>'
                  f'<td class="barcell"><span class="mbar"><span style="width:{pct}%;background:{color}"></span></span>'
                  f'<span class="pct">{pct}%</span></td></tr>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BRFD Training Analysis</title>
<style>:root{{--ink:#1a1a1a;--mut:#5c5c5c;--line:#e2e2e2;--red:#C1121F;--card:#faf9f7}}
*{{box-sizing:border-box}}body{{font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);margin:0;background:#f4f3f1}}
.page{{max-width:820px;margin:0 auto;background:#fff;padding:44px 52px;box-shadow:0 1px 6px rgba(0,0,0,.08)}}
header{{border-bottom:3px solid var(--red);padding-bottom:14px;margin-bottom:22px}}
.kick{{color:var(--red);font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:12px}}
h1{{font-size:26px;margin:4px 0 2px}}.sub{{color:var(--mut);font-size:13px}}
h2{{font-size:16px;margin:30px 0 10px;padding-bottom:5px;border-bottom:1px solid var(--line)}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 10px;text-align:center}}
.kpi .v{{font-size:24px;font-weight:800}}.kpi .l{{font-size:11px;color:var(--mut);margin-top:2px;line-height:1.25}}
.chart{{width:100%;height:auto;margin-top:6px}}.chart .ax{{font-size:10px;fill:#8a8a8a}}.chart .bl{{font-size:10px;fill:#444;font-weight:600}}
.legend{{font-size:12px;color:var(--mut);margin:8px 0 0}}.sw{{display:inline-block;width:11px;height:11px;border-radius:2px;vertical-align:-1px;margin:0 4px 0 12px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}}td.num,th.num{{text-align:right;width:64px}}.tn{{font-weight:600}}
.barcell{{width:180px;white-space:nowrap}}.mbar{{display:inline-block;width:120px;height:9px;background:#eee;border-radius:5px;overflow:hidden;vertical-align:middle}}
.mbar span{{display:block;height:100%}}.pct{{font-size:12px;color:var(--mut);margin-left:8px}}
.callout{{background:#fff6f5;border:1px solid #f3c9c5;border-left:4px solid var(--red);border-radius:6px;padding:12px 16px;margin:14px 0;font-size:13.5px}}
ul.find{{margin:8px 0;padding-left:20px}}ul.find li{{margin:6px 0}}
.foot{{margin-top:28px;padding-top:12px;border-top:1px solid var(--line);font-size:11.5px;color:var(--mut)}}
@media print{{body{{background:#fff}}.page{{box-shadow:none;max-width:none;padding:0}}h2{{page-break-after:avoid}}}}</style></head><body><div class="page">
<header><div class="kick">Baton Rouge Fire Department · Training Division</div>
<h1>Training Program Analysis</h1>
<div class="sub">Period {k['date_from']} – {k['date_to']} · Source: First Due activity log</div></header>
<div class="kpis">
<div class="kpi"><div class="v">{k['sessions']}</div><div class="l">Training sessions</div></div>
<div class="kpi"><div class="v">{k['complete_pct']:.0f}%</div><div class="l">Closed out (complete)</div></div>
<div class="kpi"><div class="v">{k['distinct_personnel']}</div><div class="l">Personnel trained</div></div>
<div class="kpi"><div class="v">{k['attendee_events']:,}</div><div class="l">Attendee-events</div></div>
<div class="kpi"><div class="v">{k['distinct_topics']}</div><div class="l">Distinct topics</div></div></div>
<h2>Monthly activity</h2>{chart}
<div class="legend"><span class="sw" style="background:#2E7D32"></span>Complete<span class="sw" style="background:#D98A00"></span>Incomplete / open</div>
<h2>Completion by topic</h2><table><thead><tr><th>Topic</th><th class="num">Sessions</th><th>Closed out</th></tr></thead><tbody>{trows}</tbody></table>
<div class="callout"><strong>Read completion as a documentation signal, not pass/fail.</strong> First Due marks completion at the session level, so low rates on multi-session academy courses most likely reflect courses in progress or awaiting close-out, not failed training.</div>
<h2>Participation</h2><p>Sessions averaged <strong>{k['avg_attendees']:.0f} attendees</strong> (median {k['median_attendees']:.0f}); {k['attendee_events']:,} attendee-events across {k['distinct_personnel']} personnel.</p>
<div class="foot">From the First Due RMS activity log (module = Training) for {k['date_from']}–{k['date_to']}. Completion is session-level; the system does not track training hours or per-person pass/fail. Personnel names withheld.</div>
</div></body></html>"""


def main():
    c = FirstDueClient(timeout=90)
    sessions = pull(c)
    total = len(sessions)
    comp = sum(1 for s in sessions if s.get("status") == "Complete")
    att = [len(names(s)) for s in sessions]; att_total = sum(att)
    per_person = Counter(n for s in sessions for n in names(s))
    m_total = Counter(mkey(s) for s in sessions)
    m_comp = Counter(mkey(s) for s in sessions if s.get("status") == "Complete")
    keys = sorted(k for k in m_total if k != "?")
    monthly = [{"month": MONTHS[int(mk.split("-")[1]) - 1], "sessions": m_total[mk],
                "complete": m_comp.get(mk, 0), "incomplete": m_total[mk] - m_comp.get(mk, 0)} for mk in keys]
    topic_total = Counter((s.get("name") or "?").strip() for s in sessions)
    topic_comp = Counter((s.get("name") or "?").strip() for s in sessions if s.get("status") == "Complete")
    topics = [{"topic": t, "sessions": n, "complete_pct": round(topic_comp.get(t, 0)/n*100)}
              for t, n in topic_total.most_common(12)]
    k = {"sessions": total, "complete_pct": (comp/total*100) if total else 0,
         "distinct_personnel": len(per_person), "attendee_events": att_total,
         "avg_attendees": (att_total/total) if total else 0,
         "median_attendees": median(att) if att else 0, "distinct_topics": len(topic_total),
         "date_from": START, "date_to": END}
    print(f"sessions={total} complete={comp} personnel={len(per_person)} topics={len(topic_total)}")
    out = os.path.join(OUT, "BRFD_Training_Analysis.html")
    open(out, "w", encoding="utf-8").write(build_html(k, monthly, topics))
    print("wrote", out)


if __name__ == "__main__":
    main()
