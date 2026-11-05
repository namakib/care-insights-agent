"""Rule-based root-cause check (used in --offline mode, no AI needed).

For one anomaly event, compare the event days with the 28 days before it,
split by channel x category, and return the segments that moved the most.
"""

import sqlite3
from datetime import date, timedelta

# How to measure each KPI for a group of tickets, plus the per-day ticket count.
KPI_EXPR = {
    "contacts": "COUNT(*) * 1.0 / COUNT(DISTINCT created_date)",
    "csat_avg": "AVG(csat)",
    "dsat_rate": "AVG(CASE WHEN csat <= 2 THEN 1.0 ELSE 0 END)",
    "cost_per_contact": "AVG(cost_usd)",
    "refund_share": "SUM(CASE WHEN category = 'refund' THEN 1.0 ELSE 0 END) / COUNT(DISTINCT created_date)",
    "fcr_rate": "AVG(first_contact_resolved * 1.0)",
}

SEGMENT_SQL = """
SELECT channel, category,
       {expr} AS kpi_value,
       COUNT(*) * 1.0 / COUNT(DISTINCT created_date) AS tickets_per_day
FROM tickets
WHERE created_date BETWEEN ? AND ?
GROUP BY channel, category
"""


def top_segments(db_path, event, n=3):
    start = date.fromisoformat(event["start_day"])
    end = date.fromisoformat(event["end_day"])
    base_start = (start - timedelta(days=28)).isoformat()
    base_end = (start - timedelta(days=1)).isoformat()

    con = sqlite3.connect(db_path)
    sql = SEGMENT_SQL.format(expr=KPI_EXPR[event["kpi"]])
    now = {(c, g): (v, t) for c, g, v, t in con.execute(sql, (start.isoformat(), end.isoformat()))}
    before = {(c, g): (v, t) for c, g, v, t in con.execute(sql, (base_start, base_end))}
    con.close()

    moves = []
    for seg, (value, per_day) in now.items():
        if seg not in before or per_day < 1:
            continue
        old_value = before[seg][0]
        # Weight the change by segment size so tiny segments don't dominate.
        impact = (value - old_value) * per_day
        moves.append({"channel": seg[0], "category": seg[1],
                      "before": round(old_value, 2), "now": round(value, 2),
                      "impact": impact})
    moves.sort(key=lambda m: abs(m["impact"]), reverse=True)
    return moves[:n]
