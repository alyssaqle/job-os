"""Who should I message for this job? Ranks people so the most-likely-to-reply-and-help is first.

Ported from Recruiting OS (MIT, github.com/esaba12/recruiting-tool):
- tie_strength / TIE_STRENGTH_SCORE: lib/affinity.js. Inverted U from Rajkumar et al., Science 2022:
  moderate ties transmit jobs best, so "talk constantly" scores below "a few real touches".
- signal_overlap / role_category / REACHABILITY: lib/discovery.js.
- coverage + STRONG_COVERAGE_THRESHOLD: lib/networkCoverage.js.
Added here: referral-sheet and 1st-degree boosts (job-search-skills' network-finder puts the
referral sheet first), a same-role bonus, and smarter company matching.

Every point comes with a human-readable reason. It's a nudge you can override, not a filter.
"""
import re
from datetime import date, datetime

# Alternate names people list on LinkedIn. network-finder calls this out ("Block" vs "Square").
ALIASES = {
    "alphabet": "google", "meta": "facebook", "block": "square", "x": "twitter",
    "aws": "amazon", "amazon web services": "amazon",
}
_SUFFIX = r"\b(inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|gmbh|group|holdings|technologies|labs)\b\.?"


def normalize_company(name: str) -> str:
    n = (name or "").lower().replace("&", "and")
    n = re.sub(r"\(.*?\)", "", n)
    n = re.sub(_SUFFIX, "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


def same_company(a: str, b: str) -> bool:
    na, nb = normalize_company(a), normalize_company(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # "Stripe" matches "Stripe Payments"; "Meta" does not match "Metabase" (word boundary).
    short, long_ = sorted((na, nb), key=len)
    return len(short) >= 3 and long_.startswith(short + " ")


# ---- lib/affinity.js --------------------------------------------------------------
def tie_strength(interaction_count: int) -> str:
    if interaction_count == 0:
        return "cold"
    if interaction_count <= 2:
        return "weak"
    if interaction_count <= 6:
        return "moderate"
    return "strong"


TIE_STRENGTH_SCORE = {"cold": 0, "weak": 2, "moderate": 3, "strong": 1}


# ---- lib/discovery.js -------------------------------------------------------------
def role_category(title: str) -> str:
    t = (title or "").lower()
    if not t:
        return "other"
    if re.search(r"recruit|talent|sourc", t):
        return "recruiter"
    if re.search(r"chief|\bc[etof]o\b|\bvp\b|vice president|head of|founder|president|director", t):
        return "leader"
    if re.search(r"product manager|program manager", t) or t.strip() == "pm":
        return "pm"
    if re.search(r"manager|lead|principal|staff", t) and re.search(r"eng|develop|softw|tech|infra|platform|data|ml", t):
        return "manager"
    if re.search(r"engineer|developer|swe|programmer|sde", t):
        return "engineer"
    if re.search(r"manager|lead", t):
        return "manager"
    return "other"


CATEGORY_LABEL = {"engineer": "Engineer", "recruiter": "Recruiter", "manager": "Manager", "pm": "PM", "leader": "Leader", "other": "Other"}
# Reachable ICs and recruiters reply and can refer; VPs/C-suite rarely answer a cold note.
REACHABILITY = {"engineer": 2, "recruiter": 2, "manager": 1.5, "pm": 1, "leader": -1, "other": 0}


def _norm(s) -> str:
    return (s or "").strip().lower()


def signal_overlap(person: dict, me: dict) -> tuple[float, list[str]]:
    """Shared background. We only have free text for most people (title, relationship, notes),
    so match my profile's signals anywhere in that text."""
    w = me.get("weights") or {}
    hay = _norm(" ".join(str(person.get(k) or "") for k in ("title", "relationship", "notes")))
    score, reasons = 0.0, []
    for emp in me.get("past_employers") or []:
        if _norm(emp) and _norm(emp) in hay:
            score += w.get("pastEmployer", 4)
            reasons.append(f"Ex-{emp}, same as you")
    for prog in me.get("programs") or []:
        if _norm(prog) and _norm(prog) in hay:
            score += w.get("program", 3)
            reasons.append(f"Shared: {prog}")
    schools = [x for x in [me.get("school"), *(me.get("school_aliases") or [])] if _norm(x)]
    if any(_norm(x) in hay for x in schools):
        score += w.get("university", 2)
        reasons.append(f"{me['school']} alum")
    if _norm(me.get("high_school")) and _norm(me["high_school"]) in hay:
        score += w.get("hometown", 1)
        reasons.append(me["high_school"])
    elif _norm(me.get("hometown")) and _norm(me["hometown"]) in hay:
        score += w.get("hometown", 1)
        reasons.append(f"From {me['hometown']}")
    return score, reasons


def _words(s: str) -> set[str]:
    stop = {"and", "the", "of", "a", "i", "ii", "iii", "senior", "sr", "junior", "jr", "staff", "lead", "principal"}
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if len(w) > 1 and w not in stop}


def score_person(person: dict, job: dict, me: dict, interaction_count: int = 0) -> dict:
    score, reasons = 0.0, []

    if person.get("source") == "referral_sheet":
        score += 5
        reasons.append("On your referral sheet (offered to refer)")
    if person.get("degree") == 1:
        score += 3
        reasons.append("1st-degree connection")
    elif person.get("degree") == 2:
        score += 1
        reasons.append("2nd-degree (ask your mutual for an intro)")

    tie = tie_strength(interaction_count)
    score += TIE_STRENGTH_SCORE[tie]
    if tie != "cold":
        reasons.append(f"{tie.capitalize()} tie ({interaction_count} past touches)")

    s, r = signal_overlap(person, me)
    score += s
    reasons += r

    cat = role_category(person.get("title"))
    reach = REACHABILITY[cat]
    score += reach
    if reach >= 2:
        reasons.append(f"Reachable {CATEGORY_LABEL[cat].lower()}")
    elif reach < 0:
        reasons.append("Senior leader, lower reply odds")

    overlap = _words(person.get("title")) & _words(job.get("role"))
    if cat in ("engineer", "manager", "pm", "other") and len(overlap) >= 1:
        score += 1.5
        reasons.append("Works on a similar role")

    connected = person.get("connected_on") or ""
    try:
        d = datetime.strptime(connected, "%Y-%m-%d").date()
        if (date.today() - d).days <= 365:
            score += 0.5
            reasons.append("Connected in the last year")
    except ValueError:
        pass

    return {"score": round(score, 1), "reasons": reasons, "category": cat}


def rank_for_job(job: dict, people: list[dict], me: dict, interaction_counts: dict[int, int]) -> list[dict]:
    """people = everyone I know; returns the ones at this job's company, best first."""
    ranked = []
    for p in people:
        if not same_company(p.get("company", ""), job["company"]):
            continue
        ranked.append({**p, **score_person(p, job, me, interaction_counts.get(p["id"], 0))})
    return sorted(ranked, key=lambda x: x["score"], reverse=True)


# ---- lib/networkCoverage.js -------------------------------------------------------
STRONG_COVERAGE_THRESHOLD = 3


def coverage(ranked: list[dict]) -> str:
    """gap = nobody there; weak = only strangers; strong = someone worth asking."""
    if not ranked:
        return "gap"
    return "strong" if ranked[0]["score"] >= STRONG_COVERAGE_THRESHOLD else "weak"
