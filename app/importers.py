"""CSV imports.

LinkedIn: Settings > Data privacy > Get a copy of your data > Connections. You get Connections.csv,
which starts with a few "Notes:" lines before the real header:
    First Name,Last Name,URL,Email Address,Company,Position,Connected On

Referral sheet: any CSV with columns roughly like name / company / title / linkedin / notes.
(job-search-skills' network-finder reads a Google Sheet via the browser; exporting it to CSV
and importing here does the same job without a browser.)
"""
import csv
import io
from datetime import datetime

HEADER_ALIASES = {
    "name": ["name", "full name", "referrer", "contact", "person"],
    "first": ["first name", "first"],
    "last": ["last name", "last"],
    "company": ["company", "employer", "organization", "current company"],
    "title": ["position", "title", "role", "job title"],
    "linkedin_url": ["url", "linkedin", "linkedin url", "profile", "profile url"],
    "email": ["email address", "email", "e-mail"],
    "connected_on": ["connected on", "date", "added"],
    "notes": ["notes", "note", "details", "instructions", "comments"],
    "relationship": ["relationship", "how i know them", "how we met", "context"],
}


def _find_header(lines: list[str]) -> int:
    for i, line in enumerate(lines[:20]):
        low = line.lower()
        if ("first name" in low and "company" in low) or ("name" in low and "company" in low):
            return i
    return 0


def _pick(row: dict, key: str) -> str:
    lowered = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    for alias in HEADER_ALIASES[key]:
        if lowered.get(alias):
            return lowered[alias]
    return ""


def _date(s: str) -> str:
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def parse(text: str, source: str) -> list[dict]:
    lines = text.lstrip("﻿").splitlines()
    start = _find_header(lines)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    people = []
    for row in reader:
        name = _pick(row, "name") or " ".join(x for x in (_pick(row, "first"), _pick(row, "last")) if x)
        if not name:
            continue
        people.append({
            "name": name,
            "company": _pick(row, "company"),
            "title": _pick(row, "title"),
            "linkedin_url": _pick(row, "linkedin_url"),
            "email": _pick(row, "email"),
            "connected_on": _date(_pick(row, "connected_on")),
            "notes": _pick(row, "notes"),
            "relationship": _pick(row, "relationship"),
            "source": source,
            "degree": 1 if source == "connections" else None,
        })
    return people


def upsert_people(conn, people: list[dict]) -> dict:
    """Match on LinkedIn URL, else name+company. Updates title/company (people change jobs)."""
    added = updated = 0
    for p in people:
        existing = None
        if p["linkedin_url"]:
            existing = conn.execute("SELECT id FROM people WHERE linkedin_url = ?", (p["linkedin_url"],)).fetchone()
        if not existing:
            existing = conn.execute(
                "SELECT id FROM people WHERE lower(name) = lower(?) AND lower(company) = lower(?)",
                (p["name"], p["company"]),
            ).fetchone()
        if existing:
            conn.execute(
                """UPDATE people SET company = COALESCE(NULLIF(?, ''), company), title = COALESCE(NULLIF(?, ''), title),
                   email = COALESCE(NULLIF(?, ''), email), connected_on = COALESCE(NULLIF(?, ''), connected_on),
                   linkedin_url = COALESCE(NULLIF(?, ''), linkedin_url),
                   degree = COALESCE(?, degree),
                   source = CASE WHEN ? = 'referral_sheet' THEN 'referral_sheet' ELSE source END,
                   notes = CASE WHEN ? != '' THEN ? ELSE notes END,
                   relationship = COALESCE(NULLIF(?, ''), relationship)
                   WHERE id = ?""",
                (p["company"], p["title"], p["email"], p["connected_on"], p["linkedin_url"], p["degree"],
                 p["source"], p["notes"], p["notes"], p["relationship"], existing["id"]),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO people (name, company, title, linkedin_url, email, source, degree, connected_on, relationship, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["name"], p["company"], p["title"], p["linkedin_url"], p["email"], p["source"], p["degree"],
                 p["connected_on"], p["relationship"], p["notes"]),
            )
            added += 1
    return {"added": added, "updated": updated}
