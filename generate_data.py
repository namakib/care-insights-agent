"""Step 1: create realistic (fake) customer-care tickets in a SQLite database.

90 days of tickets across chat, phone and email. Three problems are planted
in the data so the pipeline has something real to find:

  1. Payment outage   - phone contacts about payment issues triple for 2 days.
  2. Refund delays    - from day 70, chat customers asking about refunds get
                        unhappy (low CSAT) and refund contacts go up.
  3. Email slowdown   - from day 80, email handle time doubles, so cost
                        per contact goes up.

Run:  python generate_data.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "care.db"
START = date(2026, 7, 1)
DAYS = 90
SEED = 42

CHANNELS = {"chat": 0.45, "phone": 0.30, "email": 0.25}
CATEGORIES = {
    "booking_change": 0.28,
    "refund": 0.18,
    "payment_issue": 0.14,
    "cancellation": 0.16,
    "account": 0.12,
    "other": 0.12,
}
TIERS = {"new": 0.35, "returning": 0.45, "loyalty": 0.20}
# Agent cost per minute of handling, by channel (USD).
COST_PER_MIN = {"chat": 0.55, "phone": 0.90, "email": 0.40}
BASE_MINUTES = {"chat": 9, "phone": 12, "email": 14}


def pick(rng, weights):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def make_ticket(rng, day_index, day, channel=None, category=None):
    channel = channel or pick(rng, CHANNELS)
    category = category or pick(rng, CATEGORIES)
    tier = pick(rng, TIERS)

    minutes = max(2.0, rng.gauss(BASE_MINUTES[channel], 3))
    csat = rng.choices([1, 2, 3, 4, 5], weights=[4, 6, 15, 35, 40])[0]
    fcr = 1 if rng.random() < 0.72 else 0

    # Planted problem 2: refund delays hurt chat customers from day 70.
    if day_index >= 70 and channel == "chat" and category == "refund":
        csat = rng.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        fcr = 1 if rng.random() < 0.35 else 0
        minutes *= 1.3

    # Planted problem 3: email takes much longer from day 80.
    if day_index >= 80 and channel == "email":
        minutes *= 2.0

    return {
        "created_date": day.isoformat(),
        "channel": channel,
        "category": category,
        "customer_tier": tier,
        "csat": csat,
        "handle_minutes": round(minutes, 1),
        "cost_usd": round(minutes * COST_PER_MIN[channel], 2),
        "first_contact_resolved": fcr,
    }


def generate():
    rng = random.Random(SEED)
    tickets = []
    for i in range(DAYS):
        day = START + timedelta(days=i)
        weekend = day.weekday() >= 5
        volume = int(rng.gauss(48 if weekend else 58, 5))
        tickets += [make_ticket(rng, i, day) for _ in range(volume)]

        # Planted problem 1: payment outage on days 50-51.
        if i in (50, 51):
            tickets += [make_ticket(rng, i, day, "phone", "payment_issue") for _ in range(25)]

        # Planted problem 2 (volume side): extra refund chats from day 70.
        if i >= 70:
            tickets += [make_ticket(rng, i, day, "chat", "refund") for _ in range(6)]
    return tickets


def save(tickets):
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE tickets (
            ticket_id INTEGER PRIMARY KEY,
            created_date TEXT,          -- YYYY-MM-DD
            channel TEXT,               -- chat | phone | email
            category TEXT,              -- booking_change | refund | payment_issue | ...
            customer_tier TEXT,         -- new | returning | loyalty
            csat INTEGER,               -- 1 (very unhappy) .. 5 (very happy)
            handle_minutes REAL,
            cost_usd REAL,
            first_contact_resolved INTEGER  -- 1 = solved on first contact
        )"""
    )
    con.executemany(
        """INSERT INTO tickets (created_date, channel, category, customer_tier, csat,
               handle_minutes, cost_usd, first_contact_resolved)
           VALUES (:created_date, :channel, :category, :customer_tier, :csat,
               :handle_minutes, :cost_usd, :first_contact_resolved)""",
        tickets,
    )
    con.commit()
    con.close()


if __name__ == "__main__":
    rows = generate()
    save(rows)
    print(f"Created {len(rows):,} tickets over {DAYS} days in {DB_PATH}")
