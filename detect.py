"""Step 3: find unusual days in the KPIs.

For every day, compare each KPI with its own last 28 days. If today is more
than 3 standard deviations worse than that normal range (a "z-score" of 3),
or 2+ worse for three days running, the day is flagged. Flags for the same KPI that are at most 5 days apart are
grouped into one event so the report stays short.
"""

import sqlite3
import statistics
from pathlib import Path

ROOT = Path(__file__).parent
KPI_SQL = (ROOT / "sql" / "daily_kpis.sql").read_text()

BASELINE_DAYS = 28
MERGE_GAP_DAYS = 5      # flags this close together count as one event
Z_THRESHOLD = 3.0      # spike rule
SHIFT_THRESHOLD = 2.0  # shift rule: this many std devs...
SHIFT_DAYS = 3         # ...for this many days in a row
KPIS = ["contacts", "csat_avg", "dsat_rate", "cost_per_contact", "refund_share", "fcr_rate"]
# Which direction is bad news for each KPI.
BAD_IF_HIGHER = {"contacts": True, "csat_avg": False, "dsat_rate": True,
                 "cost_per_contact": True, "refund_share": True, "fcr_rate": False}


def load_daily_kpis(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(KPI_SQL)]
    con.close()
    return rows


def find_anomalies(daily):
    """Two rules, both standard in control charts:
    - Spike: one day is 3+ standard deviations worse than normal.
    - Shift: three days in a row are each 2+ standard deviations worse
      (catches a steady change that is too small to be a single spike).
    """
    flags = []
    for kpi in KPIS:
        bad_streak = 0
        for i in range(BASELINE_DAYS, len(daily)):
            history = [d[kpi] for d in daily[i - BASELINE_DAYS:i]]
            mean = statistics.mean(history)
            spread = statistics.stdev(history) or 1e-9
            z = (daily[i][kpi] - mean) / spread
            badness = z if BAD_IF_HIGHER[kpi] else -z  # positive = worse
            bad_streak = bad_streak + 1 if badness >= SHIFT_THRESHOLD else 0
            rule = "spike" if badness >= Z_THRESHOLD else "shift" if bad_streak >= SHIFT_DAYS else None
            if rule:
                flags.append({"day_index": i, "day": daily[i]["day"], "kpi": kpi, "rule": rule,
                              "value": daily[i][kpi], "baseline": round(mean, 3),
                              "z_score": round(z, 1)})
    return group_into_events(flags)


def group_into_events(flags):
    """Merge flags for the same KPI that are close together into one event."""
    events = []
    for f in sorted(flags, key=lambda f: (f["kpi"], f["day_index"])):
        last = events[-1] if events else None
        if last and last["kpi"] == f["kpi"] and f["day_index"] <= last["_last_index"] + MERGE_GAP_DAYS:
            last["end_day"] = f["day"]
            last["_last_index"] = f["day_index"]
            if abs(f["z_score"]) > abs(last["z_score"]):
                last.update(value=f["value"], baseline=f["baseline"], z_score=f["z_score"])
        else:
            events.append({"kpi": f["kpi"], "rule": f["rule"], "start_day": f["day"], "end_day": f["day"],
                           "value": f["value"], "baseline": f["baseline"],
                           "z_score": f["z_score"], "_last_index": f["day_index"]})
    for e in events:
        e.pop("_last_index")
    return sorted(events, key=lambda e: e["start_day"])
