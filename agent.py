"""Step 4: the Claude agent.

Claude gets the list of anomaly events and one tool, `run_sql`, which runs
read-only SQL against the tickets table. Claude decides which queries to run
to find the root cause of each event, then writes the weekly insight report.

This is a hand-written agent loop:
  1. Send the task to Claude.
  2. If Claude asks to run SQL, run it and send back the result.
  3. Repeat until Claude returns the finished report.
"""

import json
import sqlite3

import anthropic

MODEL = "claude-opus-5-5"
MAX_TURNS = 20
MAX_ROWS = 200

SCHEMA = """Table `tickets` (one row per customer-care contact):
  ticket_id INTEGER, created_date TEXT (YYYY-MM-DD),
  channel TEXT (chat | phone | email),
  category TEXT (booking_change | refund | payment_issue | cancellation | account | other),
  customer_tier TEXT (new | returning | loyalty),
  csat INTEGER (1 very unhappy .. 5 very happy; DSAT = csat <= 2),
  handle_minutes REAL, cost_usd REAL,
  first_contact_resolved INTEGER (1 = solved on first contact)"""

SYSTEM_PROMPT = f"""You are a Customer Care analytics agent. You investigate KPI anomalies \
in a support-ticket database and write a short weekly insight report for Customer Care \
leadership.

{SCHEMA}

Use the run_sql tool (SQLite dialect, SELECT only) to find the root cause of each anomaly: \
break the affected KPI down by channel, category, customer tier and date, and compare the \
anomaly period with the weeks before it. Some alerts can be noise; if the data shows no \
concentrated driver, say so instead of inventing a cause. Every claim in the report must \
come from a query result.

Write the report in Markdown with:
- **Summary**: 2-3 sentences for an executive.
- One section per real issue: What happened (with numbers), Root cause (with evidence), \
Business impact (cost, customer sentiment, loyalty risk), Recommended action, Confidence.
- A short "Alerts judged to be noise" list, if any.
Return only the report."""

TOOLS = [{
    "name": "run_sql",
    "description": "Run one read-only SQL SELECT query on the tickets table and return up "
                   f"to {MAX_ROWS} rows as JSON. Use it to break KPIs down and test hypotheses.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A single SQLite SELECT query."}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}]


def run_sql(db_path, query):
    """Execute a query on a read-only connection; return JSON text or raise ValueError."""
    if not query.lstrip().lower().startswith(("select", "with")):
        raise ValueError("Only SELECT queries are allowed.")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # read-only: cannot change data
    try:
        cur = con.execute(query)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchmany(MAX_ROWS)]
    except sqlite3.Error as err:
        raise ValueError(f"SQL error: {err}") from err
    finally:
        con.close()
    return json.dumps(rows)


def investigate(db_path, events, verbose=True):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    task = ("These KPI anomalies were flagged by the monitoring step "
            "(z-score vs the previous 28 days):\n\n" + json.dumps(events, indent=2) +
            "\n\nInvestigate each one and write the weekly insight report.")
    messages = [{"role": "user", "content": task}]

    for turn in range(MAX_TURNS):
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": "medium"},
            # If a request is ever declined, let the API retry it on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request.")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Response was cut off (max_tokens).")

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            return "".join(b.text for b in response.content if b.type == "text")

        # Keep Claude's full reply (including its tool requests) in the conversation.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for call in tool_calls:
            query = call.input.get("query", "")
            if verbose:
                print(f"  [turn {turn + 1}] SQL: {' '.join(query.split())[:110]}")
            try:
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": run_sql(db_path, query)})
            except ValueError as err:
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": str(err), "is_error": True})
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Agent did not finish within {MAX_TURNS} turns.")
