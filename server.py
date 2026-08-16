#!/usr/bin/env python3
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("LEAPS_DB", DATA_DIR / "leaps.sqlite3"))
PORT = int(os.environ.get("PORT", "8787"))
BASE_PATH = "/" + os.environ.get("LEAPS_BASE_PATH", "").strip("/")
if BASE_PATH == "/":
    BASE_PATH = ""
WHOOP_API = "https://api.prod.whoop.com/developer/v2"
WHOOP_AUTHORIZE = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_SCOPES = "offline read:cycles read:sleep read:recovery read:body_measurement"
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_FIT_API = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
GOOGLE_FIT_SCOPE = "https://www.googleapis.com/auth/fitness.body.read"
LOCAL_TZ = ZoneInfo(os.environ.get("LEAPS_TIMEZONE", "Asia/Singapore")) if ZoneInfo else timezone(timedelta(hours=8), "Asia/Singapore")
WEEKLY_WHOOP_GOALS = ("strain", "weekly_sleep", "weekly_recovery")
SOCIAL_ROLLING_GOALS = ("family_calls", "ams_friends", "sg_outings")
PROJECT_START_DATE = date(2026, 8, 1)
PROJECT_START = PROJECT_START_DATE.isoformat()


def mounted_path(path="/"):
    return f"{BASE_PATH}{path}"


def unmounted_path(path):
    if not BASE_PATH:
        if path.startswith("/leaps/"):
            return path[len("/leaps"):]
        return path
    if path == BASE_PATH:
        return "/"
    if path.startswith(BASE_PATH + "/"):
        return path[len(BASE_PATH):]
    return None


GOALS = [
    {
        "id": "weight",
        "category": "Wellness",
        "title": "Reduce weight to 79kg",
        "target_value": 79,
        "target_unit": "kg",
        "baseline_value": 85.9,
        "baseline_label": "85.9kg on Aug 2026",
        "direction": "down",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Whoop / Renpho",
        "plan": [
            "No food after 9pm",
            "No bread and heavy carbs",
            "No sweets, including office snacks",
            "No sugary drinks",
            "Go to gym 6 days/week",
            "Achieve strain target 6 days/week",
        ],
    },
    {
        "id": "bmi",
        "category": "Wellness",
        "title": "Reduce BMI to 24",
        "target_value": 24,
        "target_unit": "BMI",
        "baseline_value": 27.1,
        "baseline_label": "27.1 on Aug 2026",
        "direction": "down",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Whoop / Renpho",
        "plan": ["Same plan as weight"],
    },
    {
        "id": "strain",
        "category": "Wellness",
        "title": "Achieve daily strain target at least 6 days/week",
        "target_value": 6,
        "target_unit": "days/week",
        "baseline_value": 2,
        "baseline_label": "2 days/week",
        "direction": "up",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Whoop",
        "plan": ["Go to gym 6 days/week"],
    },
    {
        "id": "weekly_sleep",
        "category": "Wellness",
        "title": "Weekly average sleep performance >= 80%",
        "target_value": 80,
        "target_unit": "%",
        "baseline_value": 65,
        "baseline_label": "About 65%",
        "direction": "up",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Whoop",
        "plan": [
            "Go to sleep by 11pm",
            "Drink at least 2L water per night",
        ],
    },
    {"id":"weekly_recovery","category":"Wellness","title":"Weekly average recovery >= 80%","target_value":80,"target_unit":"%","baseline_value":65,"baseline_label":"About 65%","direction":"up","sample_type":"number","cadence":"weekly","source":"Whoop","plan":["Solve the AC problem with Angel","No alcohol"]},
    {
        "id": "supplements",
        "category": "Wellness",
        "title": "Take 100% of expected supplements intake",
        "target_value": 100,
        "target_unit": "%",
        "baseline_value": 5,
        "baseline_label": "About 5%",
        "direction": "up",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Manual",
        "plan": [
            "Vitamin D3: 1,000 IU at breakfast",
            "Omega-3: 1000 mg at breakfast",
            "Creatine monohydrate: 5 mg at breakfast",
            "Magnesium glycinate: 200-300 mg elemental magnesium 60-90 min before bed",
            "Probiotic 50 Billion CFU Enzyme Supplement",
        ],
    },
    {
        "id": "books",
        "category": "Personal Growth",
        "title": "Read 10 new books before end of year",
        "target_value": 10,
        "target_unit": "books",
        "baseline_value": 0,
        "baseline_label": "No books in 2026 Q2",
        "direction": "up",
        "sample_type": "number",
        "cadence": "monthly",
        "source": "Goodreads",
        "plan": [
            "Always have 1-2 active books",
            "Always bring a current book",
            "Read a bit in the evening",
            "Record progress on Goodreads",
        ],
    },
    {
        "id": "ultralearn",
        "category": "Personal Growth",
        "title": "Complete 8 UltraLearn modules before end of year",
        "target_value": 8,
        "target_unit": "modules",
        "baseline_value": 0,
        "baseline_label": "0",
        "direction": "up",
        "sample_type": "number",
        "cadence": "monthly",
        "source": "UltraLearn",
        "plan": ["Keep UltraLearn updated", "Allocate time during the week and weekend"],
    },
    {
        "id": "medium",
        "category": "Personal Growth",
        "title": "Read at least 10 Medium articles every week",
        "target_value": 10,
        "target_unit": "articles/week",
        "baseline_value": 3,
        "baseline_label": "About 3/week",
        "direction": "up",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Medium",
        "plan": ["Use small leftover times like the MRT"],
    },
    {
        "id": "apartment",
        "category": "Me & Angel",
        "title": "Move to a larger apartment before end of year",
        "target_value": 100,
        "target_unit": "%",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "milestone",
        "cadence": "monthly",
        "source": "Manual",
        "plan": [
            "Work with current agent to find new tenant",
            "Find new place",
            "Move",
        ],
    },
    {
        "id": "wedding",
        "category": "Me & Angel",
        "title": "Finalize wedding time and venue",
        "target_value": 100,
        "target_unit": "%",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "milestone",
        "cadence": "monthly",
        "source": "Manual",
        "plan": ["Shortlist options", "Choose with Angel"],
    },
    {
        "id": "family_calls",
        "category": "Social Growth",
        "title": "At least one phone call with a family member weekly",
        "target_value": 1,
        "target_unit": "calls/week",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "number",
        "cadence": "weekly",
        "source": "Manual",
        "plan": ["Track weekly calls"],
    },
    {
        "id": "sg_outings",
        "category": "Social Growth",
        "title": "At least one outing/month with a Singapore friend",
        "target_value": 1,
        "target_unit": "outings/month",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "number",
        "cadence": "monthly",
        "source": "Manual",
        "plan": ["Track outings"],
    },
    {
        "id": "ams_friends",
        "category": "Social Growth",
        "title": "At least one connect with an Amsterdam friend every 2 weeks",
        "target_value": 1,
        "target_unit": "connects/2 weeks",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "number",
        "cadence": "biweekly",
        "source": "Manual",
        "plan": ["Track friend connects"],
    },
    {
        "id": "equity_reallocation",
        "category": "Personal Finances",
        "title": "Complete the re-allocation of equity funds as per plan",
        "target_value": 100,
        "target_unit": "%",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "milestone",
        "cadence": "monthly",
        "source": "Manual",
        "plan": ["Track completion against the finance plan"],
    },
    {
        "id": "finance_tracker",
        "category": "Personal Finances",
        "title": "Update tracker automation for trends and monthly burn-rate",
        "target_value": 100,
        "target_unit": "%",
        "baseline_value": 0,
        "baseline_label": "To be done",
        "direction": "up",
        "sample_type": "milestone",
        "cadence": "monthly",
        "source": "Manual",
        "plan": ["Track automation completion"],
    },
]

GOAL_PRESENTATION = {
    "bmi": ("Reduce BMI to 24", "Bring body mass index down to 24 through steady weight and health habits."),
    "strain": ("Strain 15+, 6 days a week", "Reach a daily WHOOP strain of at least 15 on six days each week."),
    "supplements": ("Never miss supplements", "Complete every planned daily supplement intake."),
    "weekly_recovery": ("Weekly recovery performance 80+", "Maintain an average WHOOP recovery score of 80% or higher each completed week."),
    "weekly_sleep": ("Weekly sleep performance 80+", "Maintain an average WHOOP sleep performance of 80% or higher each completed week."),
    "weight": ("Weight 79kg", "Reach and maintain a body weight of 79 kg."),
    "books": ("Read 10 books", "Finish ten new books before the end of the year."),
    "medium": ("10 Medium articles every week", "Read at least ten Medium articles in each calendar week."),
    "ultralearn": ("Complete 8 UltraLearn modules", "Finish eight UltraLearn modules before year end."),
    "apartment": ("Move to New Home", "Find and move into a larger home with Angel before year end."),
    "wedding": ("Organize Wedding", "Confirm the wedding timing, venue, and essential arrangements."),
    "ams_friends": ("Connect to Ex-SG Friends every 2 weeks", "Have a meaningful catch-up with an ex-Singapore friend every two weeks."),
    "family_calls": ("Call family weekly", "Make at least one phone call with a family member every week."),
    "equity_reallocation": ("Complete assets reallocation", "Finish the planned reallocation of equity and other assets."),
    "finance_tracker": ("Update Finance Tracker", "Keep the finance tracker and monthly burn-rate automation current."),
    "kid_plan": ("Plan for our kid", "Create a shared plan for welcoming and supporting our future child."),
}
GOAL_RULES = {
    "weight": {"cadence": "daily", "source": "WHOOP"},
    "bmi": {"cadence": "daily", "source": "WHOOP calculated"},
    "strain": {"cadence": "weekly", "source": "WHOOP"},
    "weekly_sleep": {"cadence": "weekly", "source": "WHOOP"},
    "weekly_recovery": {"cadence": "weekly", "source": "WHOOP"},
    "supplements": {"target_value": 99, "cadence": "daily", "source": "Daily check-ins"},
}
GOALS.extend([
    {"id":"kid_plan","category":"Me & Angel","title":"Plan for our kid","target_value":100,"target_unit":"%","baseline_value":0,"baseline_label":"Not started","direction":"up","sample_type":"milestone","cadence":"monthly","source":"Manual","plan":["Discuss the timeline","Create a shared preparation plan"]},
])


SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  target_value REAL NOT NULL,
  target_unit TEXT NOT NULL,
  baseline_value REAL NOT NULL,
  baseline_label TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
  sample_type TEXT NOT NULL,
  cadence TEXT NOT NULL,
  source TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  baseline_configured INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
  sample_date TEXT NOT NULL,
  value REAL NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manual',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  external_key TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_goal_date ON samples(goal_id, sample_date);
CREATE TABLE IF NOT EXISTS imports (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  detail_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connections (
  provider TEXT PRIMARY KEY,
  client_id TEXT NOT NULL DEFAULT '',
  client_secret TEXT NOT NULL DEFAULT '',
  redirect_uri TEXT NOT NULL DEFAULT '',
  access_token TEXT NOT NULL DEFAULT '',
  refresh_token TEXT NOT NULL DEFAULT '',
  token_expires_at TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  last_sync_at TEXT NOT NULL DEFAULT '',
  last_sync_detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS whoop_daily_metrics (
  cycle_id TEXT PRIMARY KEY,
  sample_date TEXT NOT NULL,
  strain REAL,
  sleep_performance REAL,
  recovery REAL,
  raw_json TEXT NOT NULL,
  synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS google_fit_daily_metrics (
  sample_date TEXT PRIMARY KEY,
  weight_kg REAL NOT NULL,
  bmi REAL,
  raw_json TEXT NOT NULL,
  synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goodreads_read_books (
  book_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  read_date TEXT NOT NULL,
  raw_xml TEXT NOT NULL,
  synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  level TEXT NOT NULL CHECK(level IN ('info', 'success', 'warning', 'error')),
  source TEXT NOT NULL,
  event TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS journal_entries (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE, entry_date TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supplement_checks (sample_date TEXT PRIMARY KEY, morning_taken INTEGER NOT NULL DEFAULT 0, evening_taken INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scheduled_jobs (job_name TEXT NOT NULL, run_date TEXT NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY (job_name, run_date));
CREATE INDEX IF NOT EXISTS idx_activity_logs_occurred_at ON activity_logs(occurred_at DESC);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def db():
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def log_event(level, source, event, detail=None):
    """Persist user-facing operational events without credentials or access tokens."""
    with db() as con:
        con.execute(
            "INSERT INTO activity_logs (occurred_at, level, source, event, detail_json) VALUES (?, ?, ?, ?, ?)",
            (now_iso(), level, source, event, json.dumps(detail or {})),
        )
        con.execute(
            "DELETE FROM activity_logs WHERE id NOT IN (SELECT id FROM activity_logs ORDER BY id DESC LIMIT 500)"
        )


def list_logs(limit=100):
    limit = max(1, min(int(limit), 500))
    with db() as con:
        rows = con.execute(
            "SELECT occurred_at, level, source, event, detail_json FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    logs = []
    for row in rows:
        try:
            detail = json.loads(row["detail_json"])
        except json.JSONDecodeError:
            detail = {}
        logs.append({"at": row["occurred_at"], "level": row["level"], "source": row["source"], "event": row["event"], "detail": detail})
    return logs


def init_db():
    with db() as con:
        con.executescript(SCHEMA)
        columns = {row["name"] for row in con.execute("PRAGMA table_info(samples)")}
        if "external_key" not in columns:
            con.execute("ALTER TABLE samples ADD COLUMN external_key TEXT")
        goal_columns = {row["name"] for row in con.execute("PRAGMA table_info(goals)")}
        if "description" not in goal_columns:
            con.execute("ALTER TABLE goals ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "sort_order" not in goal_columns:
            con.execute("ALTER TABLE goals ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            existing_goals = con.execute("SELECT id FROM goals WHERE archived = 0 ORDER BY category, id").fetchall()
            for position, row in enumerate(existing_goals):
                con.execute("UPDATE goals SET sort_order = ? WHERE id = ?", (position, row["id"]))
        if "baseline_configured" not in goal_columns:
            con.execute("ALTER TABLE goals ADD COLUMN baseline_configured INTEGER NOT NULL DEFAULT 0")
            con.execute("UPDATE goals SET baseline_value = 0, baseline_label = 'Not set', baseline_configured = 0")
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_samples_goal_external_key "
            "ON samples(goal_id, external_key) WHERE external_key IS NOT NULL"
        )
        ts = now_iso()
        for goal_id, (title, description) in GOAL_PRESENTATION.items():
            con.execute("UPDATE goals SET title = ?, description = ?, updated_at = ? WHERE id = ?", (title, description, ts, goal_id))
        for goal in GOALS:
            if con.execute("SELECT 1 FROM goals WHERE id = ?", (goal["id"],)).fetchone():
                continue
            con.execute(
                """
                INSERT INTO goals (
                  id, category, title, description, target_value, target_unit, baseline_value,
                  baseline_label, direction, sample_type, cadence, source, plan_json,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal["id"],
                    goal["category"],
                    GOAL_PRESENTATION.get(goal["id"], (goal["title"], ""))[0],
                    GOAL_PRESENTATION.get(goal["id"], ("", ""))[1],
                    goal["target_value"],
                    goal["target_unit"],
                    goal["baseline_value"],
                    goal["baseline_label"],
                    goal["direction"],
                    goal["sample_type"],
                    goal["cadence"],
                    goal["source"],
                    json.dumps(goal["plan"]),
                    ts,
                    ts,
                ),
            )
        for goal_id, rules in GOAL_RULES.items():
            columns = ", ".join(f"{column} = ?" for column in rules)
            con.execute(f"UPDATE goals SET {columns}, updated_at = ? WHERE id = ?", (*rules.values(), ts, goal_id))
        con.execute("UPDATE goals SET baseline_value = 0, baseline_label = 'Not set', updated_at = ? WHERE baseline_configured = 0", (ts,))
        old_supplement_plan = json.dumps([
            "Vitamin D3: 1,000 IU at breakfast",
            "Omega-3: 1000 mg at breakfast",
            "Creatine monohydrate: 5 mg at breakfast",
            "Magnesium glycinate: 200-300 mg elemental magnesium 60-90 min before bed",
        ])
        combined_supplement_plan = json.dumps([
            "Vitamin D3: 1,000 IU at breakfast",
            "Omega-3: 1000 mg at breakfast",
            "Creatine monohydrate: 5 mg at breakfast",
            "Magnesium glycinate and Probiotic before bed",
        ])
        con.execute(
            "UPDATE goals SET plan_json = ?, updated_at = ? WHERE id = 'supplements' AND plan_json IN (?, ?)",
            (json.dumps(next(goal["plan"] for goal in GOALS if goal["id"] == "supplements")), ts, old_supplement_plan, combined_supplement_plan),
        )
        con.execute("DELETE FROM samples WHERE sample_date < ?", (PROJECT_START,))
        con.execute("DELETE FROM whoop_daily_metrics WHERE sample_date < ?", (PROJECT_START,))
        con.execute("DELETE FROM google_fit_daily_metrics WHERE sample_date < ?", (PROJECT_START,))
        con.execute("DELETE FROM goodreads_read_books WHERE read_date < ?", (PROJECT_START,))
        con.execute("DELETE FROM supplement_checks WHERE sample_date < ?", (PROJECT_START,))
        con.execute("UPDATE goals SET archived = 1, updated_at = ? WHERE id IN ('sleep_recovery', 'engagement_ring')", (ts,))


def row_goal(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "description": row["description"],
        "targetValue": row["target_value"],
        "targetUnit": row["target_unit"],
        "baselineValue": row["baseline_value"],
        "baselineLabel": row["baseline_label"],
        "baselineConfigured": bool(row["baseline_configured"]),
        "direction": row["direction"],
        "sampleType": row["sample_type"],
        "cadence": row["cadence"],
        "source": row["source"],
        "plan": json.loads(row["plan_json"]),
    }


def row_sample(row):
    return {
        "id": row["id"],
        "goalId": row["goal_id"],
        "date": row["sample_date"],
        "value": row["value"],
        "note": row["note"],
        "source": row["source"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "createdAt": row["created_at"],
    }


def progress_for(goal, sample):
    if not sample or not goal["baselineConfigured"]:
        return None
    current = sample["value"]
    target = goal["targetValue"]
    start = goal["baselineValue"]
    if goal["direction"] != "down":
        pct = ((current - start) / (target - start)) * 100 if start != target else (100 if current >= target else 0)
    else:
        pct = ((start - current) / (start - target)) * 100 if start != target else (100 if current <= target else 0)
    return max(0, min(100, round(pct, 1)))


def latest_series_sample(samples, series):
    matches = [sample for sample in samples if sample.get("metadata", {}).get("series") == series]
    return matches[-1] if matches else None


def social_rolling_sample(goal_id, samples, as_of=None):
    """Average weekly social actions across the available trailing four weeks."""
    as_of = as_of or datetime.now(LOCAL_TZ).date()
    window_start = max(PROJECT_START_DATE, as_of - timedelta(days=27))
    action_days = [date.fromisoformat(sample["date"]) for sample in samples
                   if window_start <= date.fromisoformat(sample["date"]) <= as_of]
    values = []
    period_start = window_start
    while period_start <= as_of:
        period_end = min(period_start + timedelta(days=6), as_of)
        values.append(sum(period_start <= action_day <= period_end for action_day in action_days))
        period_start = period_end + timedelta(days=1)
    value = round(sum(values) / len(values), 1) if values else 0
    return {
        "id": f"social-rolling:{goal_id}:{as_of.isoformat()}",
        "goalId": goal_id,
        "date": as_of.isoformat(),
        "value": value,
        "note": f"4-week rolling average from {window_start.isoformat()} through {as_of.isoformat()}",
        "source": "calculated",
        "metadata": {"series": "rolling_4_week", "windowStart": window_start.isoformat(), "windowEnd": as_of.isoformat(), "periods": len(values)},
        "createdAt": now_iso(),
    }


def list_goals():
    with db() as con:
        goals = [row_goal(r) for r in con.execute("SELECT * FROM goals WHERE archived = 0 ORDER BY category, sort_order, id")]
        samples = {}
        for r in con.execute("SELECT * FROM samples WHERE sample_date >= ? ORDER BY sample_date ASC, created_at ASC", (PROJECT_START,)):
            samples.setdefault(r["goal_id"], []).append(row_sample(r))
        journals = {}
        for r in con.execute("SELECT * FROM journal_entries ORDER BY created_at DESC"):
            journals.setdefault(r["goal_id"], []).append({"id": r["id"], "date": r["entry_date"], "body": r["body"]})
    for goal in goals:
        goal_samples = samples.get(goal["id"], [])
        performance_samples = goal_samples
        if goal["id"] in WEEKLY_WHOOP_GOALS:
            performance_samples = [sample for sample in goal_samples if sample.get("metadata", {}).get("series") == "rolling_4_week"]
        elif goal["id"] == "supplements":
            performance_samples = [sample for sample in goal_samples if sample.get("metadata", {}).get("series") == "rolling_30_day"]
        if goal["id"] in SOCIAL_ROLLING_GOALS:
            latest_sample = social_rolling_sample(goal["id"], goal_samples)
            goal["currentLabel"] = "4-week average"
        else:
            latest_sample = performance_samples[-1] if performance_samples else None
            goal["currentLabel"] = "Current"
        goal["latestSample"] = latest_sample
        goal["currentValue"] = latest_sample["value"] if latest_sample else None
        if not goal["baselineConfigured"]:
            goal["baselineValue"] = None
            goal["baselineLabel"] = "Not set"
        goal["progressPct"] = progress_for(goal, latest_sample)
        goal["samples"] = goal_samples
        goal["journal"] = journals.get(goal["id"], [])
    return goals


def parse_body(handler):
    size = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(size) if size else b""
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return json.loads(raw.decode("utf-8") or "{}")
    if "multipart/form-data" in content_type:
        raise ValueError("Multipart upload is not supported; paste CSV or JSON into the import box.")
    return {"raw": raw.decode("utf-8")}


def require_date(value):
    if not value:
        return date.today().isoformat()
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    if parsed < PROJECT_START_DATE:
        raise ValueError(f"Tracking starts on {PROJECT_START}")
    return value


def clean_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    if not match:
        raise ValueError(f"Cannot parse numeric value from {value!r}")
    return float(match.group(0))


def insert_sample(goal_id, sample_date, value, note="", source="manual", metadata=None, external_key=None):
    sample = {
        "id": uuid.uuid4().hex,
        "goal_id": goal_id,
        "sample_date": require_date(sample_date),
        "value": clean_float(value),
        "note": str(note or ""),
        "source": str(source or "manual"),
        "metadata_json": json.dumps(metadata or {}),
        "external_key": external_key,
        "created_at": now_iso(),
    }
    with db() as con:
        exists = con.execute("SELECT 1 FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if not exists:
            raise ValueError(f"Unknown goal: {goal_id}")
        if external_key:
            existing = con.execute(
                "SELECT id FROM samples WHERE goal_id = ? AND external_key = ?", (goal_id, external_key)
            ).fetchone()
            if existing:
                con.execute(
                    """
                    UPDATE samples SET sample_date = :sample_date, value = :value, note = :note,
                    source = :source, metadata_json = :metadata_json, created_at = :created_at WHERE id = :id
                    """,
                    {**sample, "id": existing["id"]},
                )
                return existing["id"]
        con.execute(
            """
            INSERT INTO samples (id, goal_id, sample_date, value, note, source, metadata_json, external_key, created_at)
            VALUES (:id, :goal_id, :sample_date, :value, :note, :source, :metadata_json, :external_key, :created_at)
            """,
            sample,
        )
    return sample["id"]


def update_sample(sample_id, sample_date, value, note=""):
    with db() as con:
        existing = con.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
        if not existing:
            raise ValueError("Sample not found")
        con.execute(
            "UPDATE samples SET sample_date = ?, value = ?, note = ? WHERE id = ?",
            (require_date(sample_date), clean_float(value), str(note or ""), sample_id),
        )
        updated = con.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    return row_sample(updated)


def update_goal_plan(goal_id, plan):
    cleaned = [str(item).strip() for item in plan if str(item).strip()]
    with db() as con:
        if not con.execute("SELECT 1 FROM goals WHERE id = ?", (goal_id,)).fetchone():
            raise ValueError("Goal not found")
        con.execute("UPDATE goals SET plan_json = ?, updated_at = ? WHERE id = ?", (json.dumps(cleaned), now_iso(), goal_id))
    return cleaned


def update_goal_baseline(goal_id, baseline_value):
    with db() as con:
        if not con.execute("SELECT 1 FROM goals WHERE id = ?", (goal_id,)).fetchone():
            raise ValueError("Goal not found")
        if baseline_value is None or str(baseline_value).strip() == "":
            con.execute("UPDATE goals SET baseline_value = 0, baseline_label = 'Not set', baseline_configured = 0, updated_at = ? WHERE id = ?", (now_iso(), goal_id))
            return None
        value = clean_float(baseline_value)
        con.execute("UPDATE goals SET baseline_value = ?, baseline_label = 'Configured baseline', baseline_configured = 1, updated_at = ? WHERE id = ?", (value, now_iso(), goal_id))
    return value


def update_goal_order(category, goal_ids):
    if not isinstance(category, str) or not category.strip() or not isinstance(goal_ids, list):
        raise ValueError("Invalid target order")
    with db() as con:
        expected = [row["id"] for row in con.execute("SELECT id FROM goals WHERE archived = 0 AND category = ?", (category,))]
        if len(goal_ids) != len(expected) or set(goal_ids) != set(expected):
            raise ValueError("Target order does not match this category")
        for position, goal_id in enumerate(goal_ids):
            con.execute("UPDATE goals SET sort_order = ?, updated_at = ? WHERE id = ?", (position, now_iso(), goal_id))


def delete_sample(sample_id):
    with db() as con:
        existing = con.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
        if not existing:
            raise ValueError("Sample not found")
        con.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
    return row_sample(existing)

def add_journal(goal_id, body):
    body = str(body or "").strip()
    if not body: raise ValueError("Journal note cannot be empty")
    entry = {"id": uuid.uuid4().hex, "goal_id": goal_id, "entry_date": date.today().isoformat(), "body": body, "created_at": now_iso()}
    with db() as con: con.execute("INSERT INTO journal_entries (id, goal_id, entry_date, body, created_at) VALUES (:id, :goal_id, :entry_date, :body, :created_at)", entry)
    return entry

def delete_journal(entry_id):
    with db() as con:
        entry = con.execute("SELECT * FROM journal_entries WHERE id=?", (entry_id,)).fetchone()
        if not entry: raise ValueError("Journal entry not found")
        con.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
    return entry


def reset_all_samples():
    with db() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM samples").fetchone()["n"]
        con.execute("DELETE FROM samples")
        con.execute("DELETE FROM whoop_daily_metrics")
        con.execute("DELETE FROM google_fit_daily_metrics")
        con.execute("DELETE FROM goodreads_read_books")
        con.execute("DELETE FROM supplement_checks")
    return count


def reset_all_logs():
    with db() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM activity_logs").fetchone()["n"]
        con.execute("DELETE FROM activity_logs")
    return count


def refresh_supplement_performance(sample_day):
    sample_day = require_date(sample_day)
    window_start = (date.fromisoformat(sample_day) - timedelta(days=29)).isoformat()
    with db() as con:
        completed = con.execute(
            "SELECT COUNT(*) AS n FROM supplement_checks WHERE sample_date BETWEEN ? AND ? AND morning_taken = 1 AND evening_taken = 1",
            (window_start, sample_day),
        ).fetchone()["n"]
    percentage = round(completed * 100 / 30, 1)
    insert_sample(
        "supplements", sample_day, percentage,
        f"30-day supplement completion through {sample_day}", "supplements",
        {"series": "rolling_30_day", "windowStart": window_start, "windowEnd": sample_day, "completedDays": completed, "windowDays": 30},
        f"supplements:rolling30:{sample_day}",
    )
    return percentage


def quick_record(kind):
    today = date.today()
    if kind == "medium":
        week_start = today - timedelta(days=today.weekday())
        with db() as con:
            current = con.execute("SELECT MAX(value) AS value FROM samples WHERE goal_id = 'medium' AND sample_date BETWEEN ? AND ?", (week_start.isoformat(), today.isoformat())).fetchone()["value"] or 0
        value = current + 1
        sample_id = insert_sample("medium", today.isoformat(), value, f"Android widget: Medium post read ({int(value)} this week)", "android_widget")
        return {"goal": "medium", "value": value, "sampleId": sample_id}
    supplement_part = {"pills": "morning", "supplements_morning": "morning", "supplements_evening": "night"}.get(kind)
    if supplement_part:
        column = "morning_taken" if supplement_part == "morning" else "evening_taken"
        with db() as con:
            con.execute(
                f"INSERT INTO supplement_checks (sample_date, {column}, updated_at) VALUES (?, 1, ?) "
                f"ON CONFLICT(sample_date) DO UPDATE SET {column} = 1, updated_at = excluded.updated_at",
                (today.isoformat(), now_iso()),
            )
            check = con.execute("SELECT morning_taken, evening_taken FROM supplement_checks WHERE sample_date = ?", (today.isoformat(),)).fetchone()
        value = refresh_supplement_performance(today.isoformat())
        return {"goal": "supplements", "value": value, "sampleId": f"supplements:rolling30:{today.isoformat()}", "part": supplement_part, "dayComplete": bool(check["morning_taken"] and check["evening_taken"])}
    increment_specs = {
        "ultralearn": ("ultralearn", PROJECT_START_DATE, "UltraLearn course completed"),
        "ams_friends": ("ams_friends", PROJECT_START_DATE + timedelta(days=((today - PROJECT_START_DATE).days // 14) * 14), "Amsterdam friends connection"),
        "family_calls": ("family_calls", today - timedelta(days=today.weekday()), "Family call"),
        "sg_outings": ("sg_outings", today.replace(day=1), "Singapore friends outing"),
    }
    if kind in increment_specs:
        goal_id, period_start, event_name = increment_specs[kind]
        with db() as con:
            current = con.execute(
                "SELECT MAX(value) AS value FROM samples WHERE goal_id = ? AND sample_date BETWEEN ? AND ?",
                (goal_id, period_start.isoformat(), today.isoformat()),
            ).fetchone()["value"] or 0
        value = current + 1
        sample_id = insert_sample(goal_id, today.isoformat(), value, f"Android widget: {event_name} ({int(value)} this period)", "android_widget")
        return {"goal": goal_id, "value": value, "sampleId": sample_id, "periodStart": period_start.isoformat()}
    raise ValueError("Unknown quick record type")


def connection_status():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'whoop'").fetchone()
    if not row:
        return {"configured": False, "connected": False, "lastSyncAt": "", "lastSyncDetail": ""}
    return {
        "configured": bool(row["client_id"] and row["client_secret"] and row["redirect_uri"]),
        "connected": bool(row["refresh_token"]),
        "clientId": row["client_id"],
        "redirectUri": row["redirect_uri"],
        "lastSyncAt": row["last_sync_at"],
        "lastSyncDetail": row["last_sync_detail"],
    }


def goodreads_status():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'goodreads'").fetchone()
    if not row:
        return {"configured": False, "lastSyncAt": "", "lastSyncDetail": ""}
    return {"configured": bool(row["client_id"]), "feedUrl": row["client_id"], "lastSyncAt": row["last_sync_at"], "lastSyncDetail": row["last_sync_detail"]}


def save_goodreads_settings(body):
    feed_url = str(body.get("feedUrl") or "").strip()
    parsed = urlparse(feed_url)
    if parsed.scheme != "https" or parsed.netloc not in ("www.goodreads.com", "goodreads.com") or "/review/list_rss/" not in parsed.path:
        raise ValueError("Use the HTTPS RSS URL for your Goodreads read shelf")
    with db() as con:
        con.execute("""INSERT INTO connections (provider, client_id, client_secret, redirect_uri, created_at, updated_at)
          VALUES ('goodreads', ?, '', '', ?, ?) ON CONFLICT(provider) DO UPDATE SET client_id=excluded.client_id, updated_at=excluded.updated_at""", (feed_url, now_iso(), now_iso()))
    log_event("success", "Goodreads", "Read-shelf RSS feed saved")
    return goodreads_status()


def xml_text(element, name):
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return ""


def sync_goodreads():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'goodreads'").fetchone()
    if not row or not row["client_id"]:
        raise ValueError("Save your Goodreads read-shelf RSS URL first")
    log_event("info", "Goodreads", "Sync started")
    try:
        with urlopen(row["client_id"], timeout=30) as response:
            root = ElementTree.fromstring(response.read())
    except Exception as exc:
        raise ValueError(f"Could not read Goodreads RSS feed: {exc}") from exc
    saved = 0
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "item":
            continue
        book_id = xml_text(item, "id") or xml_text(item, "guid")
        title = xml_text(item, "title") or "Untitled book"
        read_at = xml_text(item, "user_read_at")
        if not book_id or not read_at:
            continue
        try:
            read_date = parsedate_to_datetime(read_at).date().isoformat()
        except (TypeError, ValueError):
            read_date = str(read_at)[:10]
            datetime.strptime(read_date, "%Y-%m-%d")
        if read_date < PROJECT_START:
            continue
        with db() as con:
            con.execute("""INSERT INTO goodreads_read_books (book_id, title, read_date, raw_xml, synced_at)
              VALUES (?, ?, ?, ?, ?) ON CONFLICT(book_id) DO UPDATE SET title=excluded.title, read_date=excluded.read_date, raw_xml=excluded.raw_xml, synced_at=excluded.synced_at""", (book_id, title, read_date, ElementTree.tostring(item, encoding="unicode"), now_iso()))
        saved += 1
    with db() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM goodreads_read_books WHERE read_date >= ?", (PROJECT_START,)).fetchone()["n"]
        detail = f"Synced {saved} books from Goodreads; {count} marked read since {PROJECT_START}."
        con.execute("UPDATE connections SET last_sync_at=?, last_sync_detail=?, updated_at=? WHERE provider='goodreads'", (now_iso(), detail, now_iso()))
    insert_sample("books", date.today().isoformat(), count, "Goodreads read shelf", "goodreads", {"feedUrl": row["client_id"]}, f"goodreads:{date.today().year}:books")
    log_event("success", "Goodreads", "Sync completed", {"booksProcessed": saved, "readThisYear": count})
    return {"imported": saved, "count": count, "detail": detail, "connection": goodreads_status()}


def google_fit_status():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'google_fit'").fetchone()
    if not row:
        return {"configured": False, "connected": False, "lastSyncAt": "", "lastSyncDetail": ""}
    detail = json.loads(row["last_sync_detail"] or "{}") if row["last_sync_detail"].startswith("{") else {}
    return {
        "configured": bool(row["client_id"] and row["client_secret"] and row["redirect_uri"]),
        "connected": bool(row["refresh_token"]), "clientId": row["client_id"], "redirectUri": row["redirect_uri"],
        "heightCm": detail.get("heightCm", ""), "lastSyncAt": row["last_sync_at"],
        "lastSyncDetail": detail.get("message", row["last_sync_detail"]),
    }


def save_google_fit_settings(body):
    client_id = str(body.get("clientId") or "").strip()
    client_secret = str(body.get("clientSecret") or "").strip()
    redirect_uri = str(body.get("redirectUri") or "").strip()
    height_cm = clean_float(body.get("heightCm"))
    with db() as con:
        current = con.execute("SELECT * FROM connections WHERE provider = 'google_fit'").fetchone()
    if not client_id or not client_secret or not redirect_uri:
        if not client_id or not redirect_uri or not current:
            raise ValueError("Google client ID, client secret, redirect URL, and height are required")
    if not 100 <= height_cm <= 250:
        raise ValueError("Height must be between 100 and 250 cm")
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Google redirect URL must be an absolute HTTPS URL")
    with db() as con:
        existing_secret = current["client_secret"] if current else ""
        con.execute(
            """INSERT INTO connections (provider, client_id, client_secret, redirect_uri, last_sync_detail, created_at, updated_at)
            VALUES ('google_fit', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET client_id=excluded.client_id, client_secret=excluded.client_secret,
            redirect_uri=excluded.redirect_uri, last_sync_detail=excluded.last_sync_detail, updated_at=excluded.updated_at""",
            (client_id, client_secret or existing_secret, redirect_uri, json.dumps({"heightCm": height_cm}), now_iso(), now_iso()),
        )
    return google_fit_status()


def google_fit_row():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'google_fit'").fetchone()
    if not row or not row["client_id"] or not row["client_secret"] or not row["redirect_uri"]:
        raise ValueError("Save Google Fit settings first")
    return row


def google_http(url, token=None, data=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    encoded = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        encoded = json.dumps(data).encode("utf-8")
    try:
        with urlopen(Request(url, data=encoded, headers=headers, method="POST" if data is not None else "GET"), timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raise ValueError(f"Google Fit request failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:500]}") from exc


def google_token(data):
    encoded = urlencode(data).encode("utf-8")
    try:
        with urlopen(Request(GOOGLE_TOKEN, data=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        raise ValueError(f"Google authorization failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:500]}") from exc


def persist_google_tokens(tokens):
    expires_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + int(tokens.get("expires_in", 3600)) - 60, timezone.utc).isoformat()
    with db() as con:
        current = con.execute("SELECT refresh_token FROM connections WHERE provider = 'google_fit'").fetchone()
        con.execute("UPDATE connections SET access_token=?, refresh_token=?, token_expires_at=?, state='', updated_at=? WHERE provider='google_fit'",
                    (tokens.get("access_token", ""), tokens.get("refresh_token") or current["refresh_token"], expires_at, now_iso()))


def google_fit_authorize_url():
    row = google_fit_row()
    state = secrets.token_urlsafe(24)
    with db() as con:
        con.execute("UPDATE connections SET state=?, updated_at=? WHERE provider='google_fit'", (state, now_iso()))
    return GOOGLE_AUTHORIZE + "?" + urlencode({"client_id": row["client_id"], "redirect_uri": row["redirect_uri"], "response_type": "code", "scope": GOOGLE_FIT_SCOPE, "access_type": "offline", "prompt": "consent", "state": state})


def complete_google_fit_oauth(code, state):
    row = google_fit_row()
    if not state or not secrets.compare_digest(state, row["state"]):
        raise ValueError("Invalid Google authorization state. Start the connection again.")
    persist_google_tokens(google_token({"code": code, "client_id": row["client_id"], "client_secret": row["client_secret"], "redirect_uri": row["redirect_uri"], "grant_type": "authorization_code"}))


def google_fit_access_token():
    row = google_fit_row()
    if row["access_token"] and row["token_expires_at"] and datetime.fromisoformat(row["token_expires_at"]) > datetime.now(timezone.utc):
        return row["access_token"]
    if not row["refresh_token"]:
        raise ValueError("Connect your Google Fit account first")
    persist_google_tokens(google_token({"refresh_token": row["refresh_token"], "client_id": row["client_id"], "client_secret": row["client_secret"], "grant_type": "refresh_token"}))
    with db() as con:
        return con.execute("SELECT access_token FROM connections WHERE provider='google_fit'").fetchone()["access_token"]


def sync_google_fit(days=90):
    days = max(1, min(int(days), 365))
    row = google_fit_row()
    detail = json.loads(row["last_sync_detail"] or "{}")
    height_m = clean_float(detail.get("heightCm")) / 100
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 86400000
    response = google_http(GOOGLE_FIT_API, google_fit_access_token(), {"startTimeMillis": start_ms, "endTimeMillis": end_ms, "aggregateBy": [{"dataTypeName": "com.google.weight"}], "bucketByTime": {"durationMillis": 86400000}})
    imported = 0
    for bucket in response.get("bucket", []):
        points = [point for dataset in bucket.get("dataset", []) for point in dataset.get("point", [])]
        values = [point.get("value", [{}])[0].get("fpVal") for point in points if point.get("value")]
        values = [value for value in values if value is not None]
        if not values:
            continue
        sample_date = datetime.fromtimestamp(int(bucket["startTimeMillis"]) / 1000, timezone.utc).date().isoformat()
        if sample_date < PROJECT_START:
            continue
        weight = values[-1]
        bmi = weight / (height_m * height_m)
        raw = {"bucket": bucket, "source": "Google Fit"}
        with db() as con:
            con.execute("INSERT INTO google_fit_daily_metrics (sample_date, weight_kg, bmi, raw_json, synced_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(sample_date) DO UPDATE SET weight_kg=excluded.weight_kg, bmi=excluded.bmi, raw_json=excluded.raw_json, synced_at=excluded.synced_at", (sample_date, weight, bmi, json.dumps(raw), now_iso()))
        insert_sample("weight", sample_date, weight, "Google Fit / Renpho weight", "google_fit", raw, f"google_fit:{sample_date}:weight")
        insert_sample("bmi", sample_date, bmi, "Calculated from Google Fit weight", "google_fit", raw, f"google_fit:{sample_date}:bmi")
        imported += 1
    message = f"Synced {imported} daily weight and BMI samples from Google Fit."
    with db() as con:
        con.execute("UPDATE connections SET last_sync_at=?, last_sync_detail=?, updated_at=? WHERE provider='google_fit'", (now_iso(), json.dumps({"heightCm": height_m * 100, "message": message}), now_iso()))
    return {"imported": imported, "detail": message, "connection": google_fit_status()}


def save_whoop_settings(body):
    client_id = str(body.get("clientId") or "").strip()
    client_secret = str(body.get("clientSecret") or "").strip()
    redirect_uri = str(body.get("redirectUri") or "").strip()
    if not client_id or not redirect_uri:
        raise ValueError("WHOOP client ID and redirect URL are required")
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("Redirect URL must be an absolute http(s) URL")
    with db() as con:
        current = con.execute("SELECT * FROM connections WHERE provider = 'whoop'").fetchone()
        if not client_secret and not current:
            raise ValueError("WHOOP client secret is required")
        con.execute(
            """
            INSERT INTO connections (provider, client_id, client_secret, redirect_uri, created_at, updated_at)
            VALUES ('whoop', ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET client_id = excluded.client_id,
              client_secret = CASE WHEN excluded.client_secret <> '' THEN excluded.client_secret ELSE connections.client_secret END,
              redirect_uri = excluded.redirect_uri, updated_at = excluded.updated_at
            """,
            (client_id, client_secret, redirect_uri, now_iso(), now_iso()),
        )
    log_event("success", "WHOOP", "App settings saved", {"redirectUri": redirect_uri})
    return connection_status()


class WhoopRequestError(ValueError):
    def __init__(self, status, url, detail):
        super().__init__(f"WHOOP request failed ({status}) for {url}: {detail}")
        self.status = status
        self.url = url


def whoop_request(url, token=None, method="GET", data=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Leaps/1.0 (+https://carlevato.net/leaps/)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(data).encode("utf-8")
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise WhoopRequestError(exc.code, url, detail) from exc
    except URLError as exc:
        raise ValueError(f"Could not reach WHOOP: {exc.reason}") from exc


def whoop_connection_row():
    with db() as con:
        row = con.execute("SELECT * FROM connections WHERE provider = 'whoop'").fetchone()
    if not row or not row["client_id"] or not row["client_secret"] or not row["redirect_uri"]:
        raise ValueError("Save WHOOP app settings first")
    return row


def whoop_access_token():
    row = whoop_connection_row()
    expires_at = row["token_expires_at"]
    if row["access_token"] and expires_at and datetime.fromisoformat(expires_at) > datetime.now(timezone.utc):
        return row["access_token"]
    if not row["refresh_token"]:
        raise ValueError("Connect your WHOOP account first")
    tokens = whoop_request(
        WHOOP_TOKEN,
        method="POST",
        data={
            "grant_type": "refresh_token", "refresh_token": row["refresh_token"],
            "client_id": row["client_id"], "client_secret": row["client_secret"], "scope": WHOOP_SCOPES,
        },
    )
    persist_whoop_tokens(tokens)
    return tokens["access_token"]


def persist_whoop_tokens(tokens):
    expires = datetime.now(timezone.utc).timestamp() + int(tokens.get("expires_in", 3600)) - 60
    expires_at = datetime.fromtimestamp(expires, timezone.utc).isoformat()
    with db() as con:
        con.execute(
            """UPDATE connections SET access_token = ?, refresh_token = ?, token_expires_at = ?,
            state = '', updated_at = ? WHERE provider = 'whoop'""",
            (tokens.get("access_token", ""), tokens.get("refresh_token", ""), expires_at, now_iso()),
        )


def whoop_authorize_url():
    row = whoop_connection_row()
    state = secrets.token_urlsafe(24)
    with db() as con:
        con.execute("UPDATE connections SET state = ?, updated_at = ? WHERE provider = 'whoop'", (state, now_iso()))
    return WHOOP_AUTHORIZE + "?" + urlencode({
        "client_id": row["client_id"], "redirect_uri": row["redirect_uri"], "response_type": "code",
        "scope": WHOOP_SCOPES, "state": state,
    })


def complete_whoop_oauth(code, state):
    row = whoop_connection_row()
    if not state or not secrets.compare_digest(state, row["state"]):
        raise ValueError("Invalid WHOOP authorization state. Start the connection again.")
    tokens = whoop_request(
        WHOOP_TOKEN, method="POST", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": row["redirect_uri"],
            "client_id": row["client_id"], "client_secret": row["client_secret"],
        }
    )
    persist_whoop_tokens(tokens)


def record_whoop_weekly_performance(week_start, week_end):
    if week_start < PROJECT_START_DATE:
        return 0
    with db() as con:
        weekly = con.execute(
            """SELECT
                 SUM(CASE WHEN strain >= 15 THEN 1 ELSE 0 END) AS strain_days,
                 COUNT(strain) AS strain_records,
                 AVG(sleep_performance) AS sleep,
                 COUNT(sleep_performance) AS sleep_records,
                 AVG(recovery) AS recovery,
                 COUNT(recovery) AS recovery_records
               FROM whoop_daily_metrics WHERE sample_date BETWEEN ? AND ?""",
            (week_start.isoformat(), week_end.isoformat()),
        ).fetchone()
    label = f"{week_start.isoformat()} to {week_end.isoformat()}"
    definitions = (
        ("strain", weekly["strain_days"] if weekly["strain_records"] else None, weekly["strain_records"], "days with strain 15+"),
        ("weekly_sleep", weekly["sleep"], weekly["sleep_records"], "average sleep performance"),
        ("weekly_recovery", weekly["recovery"], weekly["recovery_records"], "average recovery"),
    )
    recorded = 0
    for goal_id, value, records, label_name in definitions:
        if value is None:
            continue
        insert_sample(
            goal_id, week_end.isoformat(), value, f"WHOOP {label_name} for {label}", "whoop",
            {"series": "weekly", "weekStart": week_start.isoformat(), "weekEnd": week_end.isoformat(), "records": records},
            f"whoop:{goal_id}:weekly:{week_end.isoformat()}",
        )
        with db() as con:
            raw_rows = con.execute(
                "SELECT * FROM samples WHERE goal_id = ? AND source = 'whoop' AND external_key LIKE ? ORDER BY sample_date DESC, created_at DESC LIMIT 4",
                (goal_id, f"whoop:{goal_id}:weekly:%"),
            ).fetchall()
        rolling_values = [row["value"] for row in raw_rows]
        if rolling_values:
            rolling_value = round(sum(rolling_values) / len(rolling_values), 1)
            insert_sample(
                goal_id, week_end.isoformat(), rolling_value, f"4-week rolling average through {week_end.isoformat()}", "whoop",
                {"series": "rolling_4_week", "weekEnd": week_end.isoformat(), "weeks": len(rolling_values)},
                f"whoop:{goal_id}:rolling4:{week_end.isoformat()}",
            )
        recorded += 1
    return recorded


def sync_whoop(days=30, include_cycles=True, include_weekly=True):
    days = max(1, min(int(days), 365))
    log_event("info", "WHOOP", "Sync started", {"days": days, "includeCycles": include_cycles, "includeWeekly": include_weekly})
    token = whoop_access_token()
    measurements = whoop_request(f"{WHOOP_API}/user/measurement/body", token)
    weight = (measurements or {}).get("weight_kilogram")
    height = (measurements or {}).get("height_meter")
    body_samples = 0
    if weight is not None:
        sample_date = date.today().isoformat()
        raw = {"bodyMeasurements": measurements}
        insert_sample("weight", sample_date, weight, "WHOOP body measurement", "whoop", raw, f"whoop:body:{sample_date}:weight")
        body_samples += 1
        if height:
            bmi = float(weight) / (float(height) * float(height))
            insert_sample("bmi", sample_date, bmi, "Calculated from WHOOP weight and height", "whoop", raw, f"whoop:body:{sample_date}:bmi")
            body_samples += 1
    if not include_cycles:
        detail = f"Synced {body_samples} WHOOP body measurement samples."
        with db() as con:
            con.execute("UPDATE connections SET last_sync_at = ?, last_sync_detail = ?, updated_at = ? WHERE provider = 'whoop'", (now_iso(), detail, now_iso()))
        log_event("success", "WHOOP", "Body measurement sync completed", {"bodySamples": body_samples})
        return {"synced": 0, "days": days, "detail": detail, "connection": connection_status()}
    start = max(datetime.now(timezone.utc) - timedelta(days=days), datetime.combine(PROJECT_START_DATE, datetime.min.time(), timezone.utc)).timestamp()
    url = WHOOP_API + "/cycle?" + urlencode({"limit": 25, "start": datetime.fromtimestamp(start, timezone.utc).isoformat()})
    cycles = []
    while url and len(cycles) < 500:
        page = whoop_request(url, token)
        cycles.extend(page.get("records", []))
        next_token = page.get("next_token")
        url = WHOOP_API + "/cycle?" + urlencode({"limit": 25, "start": datetime.fromtimestamp(start, timezone.utc).isoformat(), "nextToken": next_token}) if next_token else None
    synced = 0
    missing_records = 0
    for cycle in cycles:
        if cycle.get("score_state") != "SCORED" or not cycle.get("id"):
            continue
        cycle_id = str(cycle["id"])
        cycle_date = str(cycle.get("end") or cycle.get("start") or date.today().isoformat())[:10]
        if cycle_date < PROJECT_START:
            continue
        try:
            sleep = whoop_request(f"{WHOOP_API}/cycle/{cycle_id}/sleep", token)
        except WhoopRequestError as exc:
            if exc.status != 404:
                raise
            sleep = {}
            missing_records += 1
        try:
            recovery = whoop_request(f"{WHOOP_API}/cycle/{cycle_id}/recovery", token)
        except WhoopRequestError as exc:
            if exc.status != 404:
                raise
            recovery = {}
            missing_records += 1
        strain = (cycle.get("score") or {}).get("strain")
        sleep_score = (sleep.get("score") or {}).get("sleep_performance_percentage")
        recovery_score = (recovery.get("score") or {}).get("recovery_score")
        raw = {"cycle": cycle, "sleep": sleep, "recovery": recovery}
        with db() as con:
            con.execute(
                """INSERT INTO whoop_daily_metrics (cycle_id, sample_date, strain, sleep_performance, recovery, raw_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(cycle_id) DO UPDATE SET sample_date=excluded.sample_date,
                strain=excluded.strain, sleep_performance=excluded.sleep_performance, recovery=excluded.recovery,
                raw_json=excluded.raw_json, synced_at=excluded.synced_at""",
                (cycle_id, cycle_date, strain, sleep_score, recovery_score, json.dumps(raw), now_iso()),
            )
        synced += 1
    weekly_samples = 0
    week_end = date.today() - timedelta(days=date.today().weekday() + 1)
    week_start = week_end - timedelta(days=6)
    if include_weekly:
        with db() as con:
            con.execute("DELETE FROM samples WHERE goal_id IN ('strain', 'weekly_sleep', 'weekly_recovery') AND source = 'whoop' AND external_key NOT LIKE 'whoop:%:weekly:%' AND external_key NOT LIKE 'whoop:%:rolling4:%'")
        weekly_samples = record_whoop_weekly_performance(week_start, week_end)
    detail = f"Synced {synced} scored WHOOP cycles and {body_samples} body measurement samples."
    if include_weekly:
        detail += f" Recorded {weekly_samples} weekly performance samples for {week_start.isoformat()} to {week_end.isoformat()}."
    if missing_records:
        detail += f" Skipped {missing_records} unavailable sleep or recovery records."
    with db() as con:
        con.execute("UPDATE connections SET last_sync_at = ?, last_sync_detail = ?, updated_at = ? WHERE provider = 'whoop'", (now_iso(), detail, now_iso()))
    log_event("success", "WHOOP", "Sync completed", {"cycles": synced, "bodySamples": body_samples, "weeklySamples": weekly_samples, "weekStart": week_start.isoformat(), "weekEnd": week_end.isoformat(), "unavailableRecords": missing_records, "days": days})
    return {"synced": synced, "days": days, "detail": detail, "connection": connection_status()}


IMPORT_ALIASES = {
    "weight": ["weight", "body weight", "whoop weight", "renpho weight"],
    "bmi": ["bmi"],
    "strain": ["strain", "strain days", "target strain days", "days strain target achieved"],
    "weekly_sleep": ["sleep", "sleep performance", "weekly sleep"],
    "weekly_recovery": ["recovery", "recovery performance", "weekly recovery"],
    "books": ["books", "book", "goodreads", "books read"],
    "ultralearn": ["ultralearn", "modules", "modules completed"],
    "medium": ["medium", "articles", "articles read"],
}


def normalize_header(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def detect_goal(row, default_goal=None):
    if default_goal:
        return default_goal
    blob = " ".join(normalize_header(v) for v in row.values())
    for goal_id, aliases in IMPORT_ALIASES.items():
        if any(alias in blob for alias in aliases):
            return goal_id
    return None


def pick(row, names):
    normalized = {normalize_header(k): v for k, v in row.items()}
    for name in names:
        if name in normalized and normalized[name] not in ("", None):
            return normalized[name]
    return None


def import_rows(source, raw, default_goal=None):
    source = normalize_header(source or "import") or "import"
    raw = raw.strip()
    if not raw:
        raise ValueError("Nothing to import")
    if raw[0] in "[{":
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("rows") or data.get("samples") or [data]
    else:
        data = list(csv.DictReader(io.StringIO(raw)))
    count = 0
    failures = []
    for idx, row in enumerate(data, 1):
        try:
            goal_id = detect_goal(row, default_goal)
            if not goal_id:
                raise ValueError("Could not infer goal")
            sample_date = pick(row, ["date", "sample date", "day", "week", "created at", "read at"]) or date.today().isoformat()
            value = pick(row, ["value", "count", "total", "progress", "weight", "bmi", "score", "percent", "percentage"])
            if value is None:
                value = pick(row, ["articles", "books", "modules", "days"])
            note = pick(row, ["note", "notes", "title", "name", "description"]) or f"Imported from {source}"
            insert_sample(goal_id, str(sample_date)[:10], value, note=note, source=source, metadata=row)
            count += 1
        except Exception as exc:
            failures.append({"row": idx, "error": str(exc)})
    with db() as con:
        con.execute(
            "INSERT INTO imports (id, source, imported_at, row_count, detail_json) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, source, now_iso(), count, json.dumps({"failures": failures[:20]})),
        )
    return {"imported": count, "failed": len(failures), "failures": failures[:20]}


class Handler(BaseHTTPRequestHandler):
    server_version = "Leaps/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def send_redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if BASE_PATH and parsed.path in ("", "/"):
            return self.send_redirect(mounted_path("/"))
        path = unmounted_path(parsed.path)
        if path is None:
            return self.send_error_json("Not found", 404)
        if path == "/api/goals":
            return self.send_json({"goals": list_goals()})
        if path == "/api/health":
            return self.send_json({"ok": True, "database": str(DB_PATH)})
        if path == "/api/export":
            return self.send_json({"exportedAt": now_iso(), "goals": list_goals()})
        if path == "/api/logs":
            params = parse_qs(parsed.query)
            return self.send_json({"logs": list_logs(params.get("limit", [100])[0])})
        if path == "/api/whoop/settings":
            return self.send_json({"connection": connection_status(), "scopes": WHOOP_SCOPES.split()})
        if path == "/api/goodreads/settings":
            return self.send_json({"connection": goodreads_status()})
        if path == "/api/whoop/connect":
            try:
                log_event("info", "WHOOP", "OAuth connection started")
                return self.send_redirect(whoop_authorize_url())
            except Exception as exc:
                log_event("error", "WHOOP", "OAuth connection could not start", {"error": str(exc)})
                return self.send_error_json(str(exc), 400)
        if path == "/api/whoop/callback":
            try:
                params = parse_qs(parsed.query)
                if params.get("error"):
                    raise ValueError(params.get("error_description", params["error"])[0])
                complete_whoop_oauth(params.get("code", [""])[0], params.get("state", [""])[0])
                log_event("success", "WHOOP", "OAuth connection completed")
                return self.send_redirect(mounted_path("/?whoop=connected"))
            except Exception as exc:
                log_event("error", "WHOOP", "OAuth connection failed", {"error": str(exc)})
                return self.send_redirect(mounted_path("/?whoop=error&message=" + urlencode({"message": str(exc)})[8:]))
        return self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            path = unmounted_path(parsed.path)
            if path is None:
                return self.send_error_json("Not found", 404)
            body = parse_body(self)
            if path == "/api/journal":
                entry = add_journal(body.get("goalId"), body.get("body")); log_event("success", "Tracker", "Journal entry added", {"goalId": entry["goal_id"]})
                return self.send_json({"ok": True, "goals": list_goals()}, 201)
            if path == "/api/quick-record":
                result = quick_record(str(body.get("kind") or ""))
                log_event("success", "Android widget", "Quick record saved", result)
                return self.send_json({"ok": True, **result, "goals": list_goals()}, 201)
            if path == "/api/samples/reset":
                count = reset_all_samples()
                log_event("warning", "Tracker", "All progress samples reset", {"deletedSamples": count})
                return self.send_json({"ok": True, "deleted": count, "goals": list_goals()})
            if path == "/api/logs/reset":
                return self.send_json({"ok": True, "deleted": reset_all_logs()})
            if path == "/api/samples":
                goal_id = body.get("goalId")
                sample_id = insert_sample(
                    goal_id,
                    body.get("date"),
                    body.get("value"),
                    body.get("note", ""),
                    body.get("source", "manual"),
                )
                log_event("success", "Tracker", "Progress sample saved", {"goalId": goal_id, "sampleId": sample_id, "date": body.get("date"), "source": body.get("source", "manual")})
                return self.send_json({"ok": True, "goals": list_goals()}, 201)
            if path.startswith("/api/samples/") and path.endswith("/delete"):
                sample_id = path[len("/api/samples/"):-len("/delete")]
                if not sample_id or "/" in sample_id:
                    return self.send_error_json("Not found", 404)
                sample = delete_sample(sample_id)
                log_event("warning", "Tracker", "Progress sample deleted", {"goalId": sample["goalId"], "sampleId": sample_id, "date": sample["date"], "source": sample["source"]})
                return self.send_json({"ok": True, "goals": list_goals()})
            if path == "/api/import":
                params = parse_qs(parsed.query)
                result = import_rows(
                    body.get("source") or params.get("source", ["import"])[0],
                    body.get("raw") or body.get("data") or "",
                    body.get("goalId") or None,
                )
                log_event("success" if not result["failed"] else "warning", "Import", "Data import completed", {"imported": result["imported"], "failed": result["failed"], "source": body.get("source") or params.get("source", ["import"])[0]})
                return self.send_json(result, 201)
            if path == "/api/whoop/settings":
                return self.send_json({"connection": save_whoop_settings(body)})
            if path == "/api/whoop/sync":
                return self.send_json(sync_whoop(body.get("days", 30)))
            if path == "/api/goodreads/settings":
                return self.send_json({"connection": save_goodreads_settings(body)})
            if path == "/api/goodreads/sync":
                return self.send_json(sync_goodreads())
            return self.send_error_json("Not found", 404)
        except Exception as exc:
            source = "WHOOP" if path.startswith("/api/whoop/") else "Goodreads" if path.startswith("/api/goodreads/") else "Tracker"
            log_event("error", source, "Request failed", {"path": path, "error": str(exc)})
            return self.send_error_json(str(exc), 400)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unmounted_path(parsed.path)
        try:
            if path == "/api/goals/order":
                body = parse_body(self)
                update_goal_order(body.get("category"), body.get("goalIds"))
                log_event("success", "Tracker", "Target order updated", {"category": body.get("category"), "count": len(body.get("goalIds", []))})
                return self.send_json({"ok": True, "goals": list_goals()})
            if path and path.startswith("/api/goals/") and path.endswith("/baseline"):
                goal_id = path[len("/api/goals/"):-len("/baseline")]
                body = parse_body(self)
                if not goal_id or "/" in goal_id:
                    return self.send_error_json("Invalid baseline update", 400)
                value = update_goal_baseline(goal_id, body.get("baselineValue"))
                log_event("success", "Tracker", "Target baseline updated", {"goalId": goal_id, "configured": value is not None})
                return self.send_json({"ok": True, "goals": list_goals()})
            if path and path.startswith("/api/goals/") and path.endswith("/plan"):
                goal_id = path[len("/api/goals/"):-len("/plan")]
                body = parse_body(self)
                if not goal_id or "/" in goal_id or not isinstance(body.get("plan"), list):
                    return self.send_error_json("Invalid plan update", 400)
                plan = update_goal_plan(goal_id, body["plan"])
                log_event("success", "Tracker", "Goal plan updated", {"goalId": goal_id, "points": len(plan)})
                return self.send_json({"ok": True, "goals": list_goals()})
            if not path or not path.startswith("/api/samples/"):
                return self.send_error_json("Not found", 404)
            sample_id = path.removeprefix("/api/samples/")
            if not sample_id or "/" in sample_id:
                return self.send_error_json("Not found", 404)
            body = parse_body(self)
            sample = update_sample(sample_id, body.get("date"), body.get("value"), body.get("note", ""))
            log_event("success", "Tracker", "Progress sample updated", {"goalId": sample["goalId"], "sampleId": sample_id, "date": sample["date"]})
            return self.send_json({"ok": True, "goals": list_goals()})
        except Exception as exc:
            log_event("error", "Tracker", "Sample update failed", {"path": path or "", "error": str(exc)})
            return self.send_error_json(str(exc), 400)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unmounted_path(parsed.path)
        try:
            if path and path.startswith("/api/journal/"):
                entry = delete_journal(path.removeprefix("/api/journal/"))
                try:
                    log_event("warning", "Tracker", "Journal entry deleted", {"goalId": entry["goal_id"]})
                except Exception as log_error:
                    print(f"Could not log journal deletion: {log_error}", file=sys.stderr)
                return self.send_json({"ok": True, "goals": list_goals()})
            if not path or not path.startswith("/api/samples/"):
                return self.send_error_json("Not found", 404)
            sample_id = path.removeprefix("/api/samples/")
            if not sample_id or "/" in sample_id:
                return self.send_error_json("Not found", 404)
            sample = delete_sample(sample_id)
            log_event("warning", "Tracker", "Progress sample deleted", {"goalId": sample["goalId"], "sampleId": sample_id, "date": sample["date"], "source": sample["source"]})
            return self.send_json({"ok": True, "goals": list_goals()})
        except Exception as exc:
            event = "Journal deletion failed" if path and path.startswith("/api/journal/") else "Sample deletion failed"
            log_event("error", "Tracker", event, {"path": path or "", "error": str(exc)})
            return self.send_error_json(str(exc), 400)

    def serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        target = (PUBLIC / path.lstrip("/")).resolve()
        if not str(target).startswith(str(PUBLIC.resolve())) or not target.exists() or target.is_dir():
            return self.send_error_json("Not found", 404)
        content = target.read_bytes()
        if target.suffix == ".html":
            content = content.replace(b"__LEAPS_BASE_PATH__", BASE_PATH.encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_scheduled_job(job_name, run_date, callback):
    with db() as con:
        already_run = con.execute("SELECT 1 FROM scheduled_jobs WHERE job_name = ? AND run_date = ?", (job_name, run_date)).fetchone()
    if already_run:
        return
    callback()
    with db() as con:
        con.execute("INSERT OR IGNORE INTO scheduled_jobs (job_name, run_date, completed_at) VALUES (?, ?, ?)", (job_name, run_date, now_iso()))


def whoop_scheduler():
    while True:
        try:
            local_now = datetime.now(LOCAL_TZ)
            run_date = local_now.date().isoformat()
            if local_now.hour >= 10:
                run_scheduled_job("supplement_performance", run_date, lambda: refresh_supplement_performance(run_date))
            connection = whoop_connection_row()
            if not connection["access_token"] and not connection["refresh_token"]:
                time.sleep(60)
                continue
            if local_now.weekday() == 0 and local_now.hour >= 8:
                run_scheduled_job("whoop_weekly", run_date, lambda: sync_whoop(30, include_cycles=True, include_weekly=True))
            if local_now.hour >= 10:
                run_scheduled_job("whoop_body", run_date, lambda: sync_whoop(1, include_cycles=False, include_weekly=False))
        except Exception as exc:
            log_event("error", "WHOOP", "Scheduled sync failed", {"error": str(exc)})
        time.sleep(60)


def main():
    init_db()
    threading.Thread(target=whoop_scheduler, name="whoop-scheduler", daemon=True).start()
    print(f"Leaps running on http://127.0.0.1:{PORT}{mounted_path('/')}")
    print(f"SQLite database: {DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
