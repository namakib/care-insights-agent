"""Run the whole pipeline: data -> KPIs -> anomalies -> report.

  python main.py            # full run: Claude agent investigates and writes the report
  python main.py --offline  # no AI: rule-based drill-down, free to run
"""

import argparse
from datetime import date
from pathlib import Path

import generate_data
from detect import find_anomalies, load_daily_kpis
from drilldown import top_segments

ROOT = Path(__file__).parent
DB_PATH = generate_data.DB_PATH
REPORTS = ROOT / "reports"

KPI_LABELS = {
    "contacts": "Contact volume (per day)",
    "csat_avg": "Average CSAT",
    "dsat_rate": "DSAT rate (share of CSAT 1-2)",
    "cost_per_contact": "Cost per contact (USD)",
    "refund_share": "Refund contacts",
    "fcr_rate": "First-contact resolution rate",
}


def offline_report(events):
    lines = [f"# Customer Care Weekly Insights (offline mode)",
             f"_Generated {date.today().isoformat()} without AI: rule-based drill-down._", ""]
    if not events:
        return "\n".join(lines + ["No anomalies detected."])
    lines.append(f"**{len(events)} anomaly events detected.**\n")
    for e in events:
        period = e["start_day"] if e["start_day"] == e["end_day"] else f"{e['start_day']} to {e['end_day']}"
        lines += [f"## {KPI_LABELS[e['kpi']]}: {period}",
                  f"- Value {e['value']} vs normal {e['baseline']} (z-score {e['z_score']}, {e['rule']} rule)",
                  "- Biggest movers (channel / category: before -> now):"]
        for m in top_segments(DB_PATH, e):
            lines.append(f"  - {m['channel']} / {m['category']}: {m['before']} -> {m['now']}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="skip the Claude agent")
    parser.add_argument("--reuse-data", action="store_true", help="don't regenerate the database")
    args = parser.parse_args()

    if not (args.reuse_data and DB_PATH.exists()):
        generate_data.save(generate_data.generate())
    daily = load_daily_kpis(DB_PATH)
    events = find_anomalies(daily)
    print(f"Computed KPIs for {len(daily)} days; {len(events)} anomaly events found.")

    if args.offline:
        report, name = offline_report(events), "weekly_report_offline.md"
    else:
        from agent import investigate  # imported here so --offline works without the SDK
        print("Claude agent is investigating...")
        report, name = investigate(DB_PATH, events), "weekly_report.md"

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / name
    out.write_text(report)
    print(f"Report saved to {out}")


if __name__ == "__main__":
    main()
