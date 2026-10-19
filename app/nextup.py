"""Low cognitive load: instead of a wall of tasks, one ordered queue and the UI shows the top card big.

Rules adapted from Recruiting OS lib/attention.js (MIT): overdue follow-ups first, then
"awaiting reply" (last touch was mine, >=5 days, no follow-up date set), then stale applications.
Added: apply-then-reach-out steps, since that's the loop this app is built around.
"""
from datetime import date, datetime

from . import ai, profile, warmpaths, workauth
from .db import rows

AWAITING_REPLY_DAYS = 5  # attention.js awaitingReply threshold
STALE_APPLICATION_DAYS = 14


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - datetime.fromisoformat(iso[:10]).date()).days
    except ValueError:
        return None


def _people_index(conn):
    people = rows(conn.execute("SELECT * FROM people"))
    counts = {r["person_id"]: r["n"] for r in conn.execute(
        "SELECT person_id, count(*) AS n FROM interactions GROUP BY person_id")}
    return people, counts


def queue(conn) -> list[dict]:
    today = date.today().isoformat()
    me = profile.me()
    items: list[dict] = []

    links = rows(conn.execute(
        """SELECT jp.*, p.name, j.company, j.role FROM job_people jp
           JOIN people p ON p.id = jp.person_id JOIN jobs j ON j.id = jp.job_id
           WHERE j.status NOT IN ('rejected', 'archived', 'offer')"""))

    # 1. Follow-ups I scheduled that are due
    for l in links:
        if l["status"] == "messaged" and l["follow_up_on"] and l["follow_up_on"] <= today:
            overdue = _days_since(l["follow_up_on"]) or 0
            tier = ai.escalation_tier(overdue + 4)  # due date is already ~4 days after the first message
            items.append({
                "kind": "follow_up", "rank": 0 - overdue, "job_id": l["job_id"], "person_id": l["person_id"],
                "title": f"Follow up with {l['name']}", "detail": f"{l['role']} at {l['company']} · follow-up #{tier}",
                "tier": tier,
            })

    # 1b. They accepted my connection request: strike while it's warm
    for l in links:
        if l["status"] == "connected":
            items.append({
                "kind": "follow_up", "rank": 1, "job_id": l["job_id"], "person_id": l["person_id"],
                "title": f"{l['name']} accepted! Send your pitch", "detail": f"{l['role']} at {l['company']}",
                "message_kind": "connected_pitch",
            })

    # 2. Messaged, nothing back, no follow-up date set (attention.js awaitingReply)
    for l in links:
        waited = _days_since(l["messaged_on"])
        if l["status"] == "messaged" and not l["follow_up_on"] and waited is not None and waited >= AWAITING_REPLY_DAYS:
            items.append({
                "kind": "follow_up", "rank": 10 - waited / 100, "job_id": l["job_id"], "person_id": l["person_id"],
                "title": f"Nudge {l['name']} (no reply in {waited} days)", "detail": f"{l['role']} at {l['company']}",
                "tier": ai.escalation_tier(waited),
            })

    jobs = rows(conn.execute(
        "SELECT * FROM jobs WHERE status NOT IN ('rejected', 'archived', 'offer') ORDER BY priority, created_at"))
    contacted = {l["job_id"] for l in links if l["status"] in ("requested", "connected", "messaged", "replied", "referred", "no_reply")}
    people, counts = _people_index(conn)

    for j in jobs:
        if (j["priority"] or 2) >= 3 and j["status"] in ("saved", "tailoring"):
            continue  # 'New roles' inbox: no nagging until I promote it (priority 1-2)
        if me.get("visa_status") and (workauth.check(j["jd"])["verdict"] == "dont_apply"
                                      or '"verdict": "Not eligible' in (j["fit_notes"] or "")):
            continue  # not eligible for my work authorization: never nag about it
        ranked = warmpaths.rank_for_job(j, people, me, counts)
        best = ranked[0] if ranked else None
        p = j["priority"] or 2

        # 3. Applied but haven't reached out: the highest-leverage step
        if j["status"] == "applied" and j["id"] not in contacted:
            items.append({
                "kind": "reach_out", "rank": 20 + p, "job_id": j["id"], "person_id": best["id"] if best else None,
                "title": f"Message {best['name']}" if best else f"Find someone at {j['company']} to message",
                "detail": f"You applied to {j['role']}. " + ("; ".join(best["reasons"][:2]) if best else "No warm path yet, open People to search."),
            })
        # 4. Not applied yet
        elif j["status"] in ("saved", "tailoring"):
            if not j["tailored_resume"]:
                items.append({"kind": "tailor", "rank": 30 + p, "job_id": j["id"],
                              "title": f"Tailor resume for {j['company']}", "detail": j["role"]})
            else:
                items.append({"kind": "apply", "rank": 25 + p, "job_id": j["id"],
                              "title": f"Apply to {j['company']}", "detail": f"{j['role']} · resume is ready"})
        # 4a. A certification is on the resume as "(in progress)": start it BEFORE submitting so that's true
        import json as _json
        certs = [x.replace(" (start before you submit)", "") for x in _json.loads(j.get("stretch_skills") or "[]")
                 if x.endswith("(start before you submit)")]
        if certs and j["status"] in ("saved", "tailoring"):
            items.append({"kind": "learn", "rank": 15 + p, "job_id": j["id"],
                          "title": f"Start {certs[0]} before applying to {j['company']}",
                          "detail": "Your resume lists it as (in progress). Enroll and start it first, ~10 minutes."})
        # 4b. Applied with skills I listed but still need to learn
        if j["status"] in ("applied", "reached_out", "interviewing") and (j.get("stretch_skills") or "[]") != "[]":
            import json as _json
            skills = _json.loads(j["stretch_skills"])
            items.append({"kind": "learn", "rank": (5 if j["status"] == "interviewing" else 35) + p, "job_id": j["id"],
                          "title": f"Learn {', '.join(skills[:3])} for {j['company']}",
                          "detail": "On your resume's Skills list. Get hands-on before any interview."})
        # 5. Stale application
        elif j["status"] == "reached_out":
            since = _days_since(j["applied_on"])
            if since is not None and since >= STALE_APPLICATION_DAYS and not j["follow_up_on"]:
                items.append({"kind": "stale", "rank": 40 + p, "job_id": j["id"],
                              "title": f"Check on {j['company']} ({since} days since applying)",
                              "detail": "Try another person, or mark it no-reply and move on."})

    return sorted(items, key=lambda x: x["rank"])
