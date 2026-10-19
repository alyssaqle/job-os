"""Pull the newest US entry-level PM / adjacent roles from SimplifyJobs' public GitHub lists (updated daily).

No LinkedIn scraping (that gets accounts restricted). These lists are public JSON with posting dates and a
sponsorship field, so it's fast and legit.
"""
import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

LISTS = {
    "Internship": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "New grad": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
}

# PM + adjacent: product, project/program, product builder, AI analyst/consultant/automation, tech consulting analyst
WANT = re.compile(
    r"\bproduct\b.*\b(manag|analyst|owner|operations|ops|builder|associate|strateg|intern)|\bAPM\b|associate product|"
    r"\b(project|program)\s+(manag|coordinat|analyst|associate|intern)|"
    r"\bAI\b.*\b(analyst|consult|strateg|automation|operations|product)|\b(analyst|consultant)\b.*\bAI\b|"
    r"(technology|tech|digital|IT)\s+(consult|analyst)|digital transformation|automation\s+(analyst|consult)",
    re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp|manager\s+(ii|iii|2|3)|phd|mba)\b", re.I)
ENGINEERING = re.compile(r"\bengineer(ing)?\b|\bdeveloper\b|\bSWE\b|\bhardware\b|\bfirmware\b", re.I)
NON_US = re.compile(r"canada|toronto|vancouver|montreal|ontario|\bUK\b|london|united kingdom|india|bangalore|bengaluru|"
                    r"germany|berlin|munich|ireland|dublin|singapore|hong kong|china|japan|tokyo|australia|sydney|"
                    r"mexico|brazil|israel|france|paris|netherlands|amsterdam|poland|spain|switzerland|sweden|korea", re.I)


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JobOS personal job tracker)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _us(locations) -> bool:
    locs = locations or []
    return bool(locs) and not all(NON_US.search(l or "") for l in locs)


def candidates(me: dict, limit: int = 100) -> list[dict]:
    avoid = [a.lower() for a in me.get("avoid_roles") or []]
    rows = []
    for kind, url in LISTS.items():
        for x in json.loads(_get(url, 60)):
            title = x.get("title") or ""
            if not (x.get("active") and x.get("is_visible", True)):
                continue
            if not (WANT.search(title) or x.get("category") in ("Product", "Product Management")):
                continue
            if ENGINEERING.search(title) and not re.search(r"product manag|program manag|project manag", title, re.I):
                continue  # Product Engineer / Software Engineer etc. are engineering jobs, not PM-adjacent
            if SENIOR.search(title) or any(a in title.lower() for a in avoid):
                continue
            if (x.get("sponsorship") or "").startswith("U.S. Citizenship"):
                continue  # requires citizenship: not eligible for a student visa
            if not _us(x.get("locations")):
                continue
            rows.append({"company": x.get("company_name") or "?", "role": title, "url": x.get("url") or "",
                         "location": "; ".join((x.get("locations") or [])[:3]), "kind": kind,
                         "posted": x.get("date_posted") or 0, "sponsorship": x.get("sponsorship") or "Other",
                         "terms": ", ".join(x.get("terms") or [])})
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["posted"], reverse=True):
        key = (r["company"].lower(), r["role"].lower())
        if key in seen or not r["url"]:
            continue
        seen.add(key)
        out.append(r)
    return out[:limit]


def page_text(url: str) -> str:
    """Best-effort job description from the posting page (works for Greenhouse/Lever/Ashby-style HTML; JS-only
    pages like Workday come back empty and get filled when I open them with the side panel)."""
    try:
        raw = _get(url, 20).decode("utf-8", "ignore")
    except Exception:
        return ""
    m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.){300,})"', raw)  # JSON-LD JobPosting
    if m:
        try:
            raw = json.loads(f'"{m.group(1)}"')
        except ValueError:
            pass
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:20000] if len(text) > 600 else ""


def with_descriptions(rows: list[dict]) -> list[dict]:
    with ThreadPoolExecutor(12) as pool:
        for r, jd in zip(rows, pool.map(lambda r: page_text(r["url"]), rows)):
            r["jd"] = jd
    return rows


def posted_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else "?"
