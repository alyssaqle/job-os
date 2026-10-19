"""LinkedIn link builders. We never scrape or log into LinkedIn; we build the search URL and you click it.

- job_search_url: ported from SnipeDin's buildURL (MIT, github.com/1Mangesh1/snipedin), same f_* params.
- people_searches: people-search URLs for one job. The 1st-degree search is the exact URL
  job-search-skills' network-finder uses (MIT, github.com/sameergdogg/job-search-skills).
"""
import json
import re
from urllib.parse import urlencode

PEOPLE = "https://www.linkedin.com/search/results/people/"
JOBS = "https://www.linkedin.com/jobs/search/"

# SnipeDin's filter values, kept verbatim so their meaning stays documented in one place.
TIME_POSTED = {"10m": "r600", "1h": "r3600", "24h": "r86400", "week": "r604800", "month": "r2592000"}
WORK_MODE = {"onsite": "1", "remote": "2", "hybrid": "3"}
JOB_TYPE = {"full_time": "F", "part_time": "P", "contract": "C", "temporary": "T", "internship": "I", "volunteer": "V"}
EXPERIENCE = {"internship": "1", "entry": "2", "associate": "3", "mid_senior": "4", "director": "5", "executive": "6"}


def job_search_url(keywords="", location="", time_posted="", sort_recent=False, work_mode=(),
                   job_type=(), experience=(), easy_apply=False) -> str:
    """Python port of SnipeDin's buildURL()."""
    params = {}
    if keywords.strip():
        params["keywords"] = keywords.strip()
    if location.strip():
        params["location"] = location.strip()
    if time_posted:
        params["f_TPR"] = TIME_POSTED.get(time_posted, time_posted)
    if sort_recent:
        params["sortBy"] = "DD"
    if work_mode:
        params["f_WT"] = ",".join(WORK_MODE.get(w, w) for w in work_mode)
    if job_type:
        params["f_JT"] = ",".join(JOB_TYPE.get(j, j) for j in job_type)
    if experience:
        params["f_E"] = ",".join(EXPERIENCE.get(e, e) for e in experience)
    if easy_apply:
        params["f_EA"] = "true"
    return f"{JOBS}?{urlencode(params)}" if params else JOBS


_SENIORITY = r"\b(senior|sr\.?|junior|jr\.?|staff|principal|lead|intern(ship)?|new grad(uate)?|entry[- ]level|associate|i{1,3}|iv|\d{4})\b"


def role_core(role: str) -> str:
    """'Senior Software Engineer II (Payments)' -> 'Software Engineer'. Used for people searches."""
    r = re.sub(r"\(.*?\)|,.*$| - .*$| – .*$", "", role or "")
    r = re.sub(_SENIORITY, "", r, flags=re.I)
    return re.sub(r"\s+", " ", r).strip() or (role or "").strip()


def manager_title(role: str) -> str:
    core = role_core(role).lower()
    if re.search(r"engineer|developer|swe|software", core):
        return "engineering manager"
    if "design" in core:
        return "design manager"
    if "product" in core:
        return "product lead"
    if "data" in core or "analyst" in core:
        return "data manager"
    return "hiring manager"


def _people_url(keywords: str, network: list[str] | None = None, company_id: str = "") -> str:
    params = {"keywords": keywords, "origin": "GLOBAL_SEARCH_HEADER"}
    if network:
        params["network"] = json.dumps(network, separators=(",", ":"))
    if company_id:
        params["currentCompany"] = json.dumps([company_id], separators=(",", ":"))
        params["origin"] = "FACETED_SEARCH"
    return f"{PEOPLE}?{urlencode(params)}"


def people_searches(job: dict, me: dict) -> list[dict]:
    """Ordered most-likely-to-reply first. Each: {label, why, url}."""
    company = job["company"].strip()
    cid = (job.get("company_linkedin_id") or "").strip()
    # With a company id LinkedIn filters exactly, so the company name can leave the keywords.
    at = "" if cid else f"{company} "
    role = role_core(job["role"])
    out = [
        {
            "label": f"My 1st-degree connections at {company}",
            "why": "Warmest path. They already know you, so a referral ask is normal.",
            "url": _people_url(company if not cid else "", ["F"], cid),
        },
        {
            "label": f"2nd-degree {role}s at {company}",
            "why": "Peers on the team. Reachable, and you can ask your mutual for an intro.",
            "url": _people_url(f"{at}{role}", ["S"], cid),
        },
        {
            "label": f"Recruiters at {company}",
            "why": "Their job is to reply. Best for 'I just applied to <req>'.",
            "url": _people_url(f"{at}recruiter", None, cid),
        },
        {
            "label": f"Likely hiring managers ({manager_title(job['role'])})",
            "why": "Can pull your resume out of the pile. Keep it short and specific.",
            "url": _people_url(f"{at}{manager_title(job['role'])}", ["S", "O"], cid),
        },
    ]
    if me.get("school"):
        out.append({
            "label": f"{me['school']} alumni at {company}",
            "why": "Shared school is one of the strongest cold-reply signals.",
            "url": _people_url(f"{at}{me['school']}", None, cid),
        })
    for emp in (me.get("past_employers") or [])[:3]:
        out.append({
            "label": f"Ex-{emp} people now at {company}",
            "why": f"You both worked at {emp}. Instant common ground.",
            "url": _people_url(f"{at}{emp}", None, cid),
        })
    out.append({
        "label": "Google X-ray (finds profiles LinkedIn search hides)",
        "why": "Works without LinkedIn's search limits.",
        "url": "https://www.google.com/search?" + urlencode({"q": f'site:linkedin.com/in "{company}" "{role}"'}),
    })
    return out
