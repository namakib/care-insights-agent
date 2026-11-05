# Customer Care Insights Agent

A small AI analytics pipeline that watches customer-care KPIs, spots unusual
changes, and uses a **Claude agent** to investigate the root cause with SQL and
write a weekly insight report with recommendations.

```
 tickets (SQL database)
        │
        ▼
 1. Metrics layer ── sql/daily_kpis.sql ── 6 daily KPIs
        │
        ▼
 2. Anomaly detection ── detect.py ── flags unusual days
        │
        ▼
 3. Claude agent ── agent.py ── writes its own SQL to find the cause
        │
        ▼
 4. Weekly insight report ── reports/weekly_report.md
```

## What it does, in plain English

1. **Data** (`generate_data.py`): creates 90 days of realistic, fake
   customer-support tickets (about 5,000) across chat, phone and email. Each
   ticket has a category (refund, booking change, payment issue…), a CSAT
   score (1–5), handling time and cost. Three real-world problems are hidden
   in the data for the pipeline to find:
   - a **payment outage** that floods the phone line for a day,
   - **refund delays** that make chat customers unhappy,
   - an **email slowdown** that doubles handling time and raises cost.

2. **Metrics layer** (`sql/daily_kpis.sql`): one SQL query turns tickets into
   six daily KPIs: contact volume, average CSAT, DSAT rate (share of unhappy
   customers), cost per contact, refund contacts and first-contact resolution.
   It is plain SQL, so it also runs on BigQuery with only the table name
   changed.

3. **Anomaly detection** (`detect.py`): each KPI is compared with its own
   previous 28 days. A day is flagged when it is much worse than normal:
   - **Spike rule:** 3+ standard deviations worse in one day.
   - **Shift rule:** 2+ standard deviations worse three days in a row
     (catches slower, steady changes).

   Flags close together are grouped into one event. On the sample data it
   finds all three hidden problems with no false alarms.

4. **Claude agent** (`agent.py`): Claude receives the list of flagged events
   and one tool, `run_sql`, that can only **read** the database. Claude decides
   which questions to ask (by channel, category, customer tier, date), runs the
   queries, checks whether an alert is real or just noise, and writes the
   report: what happened, root cause with evidence, business impact,
   recommended action and confidence.

   The agent loop is written by hand so every step is visible:
   send the task → if Claude asks for SQL, run it and send back the result →
   repeat until Claude returns the report.

**No-AI mode:** `--offline` swaps the agent for a rule-based drill-down
(`drilldown.py`) that ranks which channel/category moved most. It is free and
useful for checking the agent's conclusions.

## Run it

Needs Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py --offline          # free, no API key needed
export ANTHROPIC_API_KEY=...      # your key from console.anthropic.com
python main.py                    # Claude agent run (a few cents per run)
```

Reports are saved in `reports/`.

## Safety choices

- The SQL tool opens the database in **read-only** mode and accepts only
  `SELECT` queries, so the agent cannot change data.
- Results are capped at 200 rows per query, and the agent stops after 20 turns.
- The prompt tells Claude every claim must come from a query result, and to
  call an alert noise rather than invent a cause.

## Files

| File | Purpose |
|---|---|
| `generate_data.py` | Creates the sample ticket database |
| `sql/daily_kpis.sql` | KPI definitions (the metrics layer) |
| `detect.py` | Spike and shift anomaly rules |
| `drilldown.py` | Rule-based root-cause ranking (offline mode) |
| `agent.py` | Claude agent with the read-only SQL tool |
| `main.py` | Runs the whole pipeline |

## Ideas to extend

- Point the metrics layer at **BigQuery** using the `google-cloud-bigquery`
  client instead of SQLite.
- Run it on a schedule and post the report to Slack or email.
- Add a dashboard (Looker Studio / Tableau) on top of the daily KPI table.
