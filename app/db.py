"""SQLite storage. One file, no server, easy to back up (it's just data/jobos.db)."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("JOBOS_DB", ROOT / "data" / "jobos.db"))

STATUSES = [
    "saved",        # found it, haven't done anything
    "tailoring",    # resume in progress
    "applied",
    "reached_out",  # applied + messaged someone
    "interviewing",
    "offer",
    "rejected",
    "archived",
]

# Status of one person *for one job*
CONTACT_STATUSES = ["suggested", "to_contact", "requested", "connected", "messaged", "replied", "referred", "no_reply"]
# requested = connection request sent, waiting for accept; connected = accepted, now DM them

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    url TEXT DEFAULT '',
    url_key TEXT DEFAULT '',             -- normalized url, for "have I seen this job?"
    location TEXT DEFAULT '',
    jd TEXT DEFAULT '',
    status TEXT DEFAULT 'saved',
    priority INTEGER DEFAULT 2,          -- 1 = high, 2 = normal, 3 = low
    fit_score INTEGER,                   -- 0-100, from AI fit check
    fit_notes TEXT DEFAULT '',
    tailored_resume TEXT DEFAULT '',     -- version A (.tex)
    tailored_resume_b TEXT DEFAULT '',   -- version B (.tex), different angle + email
    applied_variants TEXT DEFAULT '',    -- "A", "B" or "A,B": which versions I actually sent
    response_variant TEXT DEFAULT '',    -- which version got a reply: A | B | both | none
    jd_keywords TEXT DEFAULT '',         -- JSON list of must-have ATS keywords
    stretch_skills TEXT DEFAULT '',      -- JSON list: skills listed on the resume that I still need to learn
    notes TEXT DEFAULT '',
    company_linkedin_id TEXT DEFAULT '', -- optional, makes LinkedIn searches exact
    applied_on TEXT,
    follow_up_on TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT DEFAULT '',
    title TEXT DEFAULT '',
    linkedin_url TEXT DEFAULT '',
    email TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',        -- connections | referral_sheet | manual | browser
    degree INTEGER,                      -- 1 = 1st-degree connection, 2, 3, NULL = unknown
    connected_on TEXT DEFAULT '',
    relationship TEXT DEFAULT '',        -- "worked together at X", "same bootcamp", ...
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS people_linkedin ON people(linkedin_url) WHERE linkedin_url != '';

CREATE TABLE IF NOT EXISTS job_people (
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'to_contact',
    last_message TEXT DEFAULT '',
    messaged_on TEXT,
    follow_up_on TEXT,
    PRIMARY KEY (job_id, person_id)
);

CREATE TABLE IF NOT EXISTS resume_chat (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                  -- me | claude
    content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY,
    person_id INTEGER REFERENCES people(id) ON DELETE CASCADE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,                  -- message | reply | call | coffee | referral | note
    body TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


MIGRATIONS = {  # columns added after the first release; ALTER TABLE for existing databases
    "jobs": {"url_key": "TEXT DEFAULT ''", "tailored_resume_b": "TEXT DEFAULT ''",
             "applied_variants": "TEXT DEFAULT ''", "response_variant": "TEXT DEFAULT ''",
             "jd_keywords": "TEXT DEFAULT ''", "stretch_skills": "TEXT DEFAULT ''"},  # JSON list, from fit check or first tailor
}


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def one(cur) -> dict | None:
    r = cur.fetchone()
    return dict(r) if r else None
