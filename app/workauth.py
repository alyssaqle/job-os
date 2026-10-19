"""Can an F-1 student (OPT/CPT) apply to this job? Instant, free, quotes the exact sentence.

My rules:
- DON'T APPLY: US citizens / permanent residents / green card only; must be authorized to work permanently or
  indefinitely; explicitly no OPT / CPT / F-1 / student visas; security clearance, ITAR, "U.S. person".
- STILL APPLY: "we don't sponsor (H-1B)" / "no visa sponsorship" when none of the above is said. OPT covers the
  internship / first job; sponsorship is a later problem.
- Equal-opportunity boilerplate ("regardless of citizenship status") never counts.
Builds on ai-job-application-kit's sponsorship-filter idea (MIT), tuned for F-1.
"""
import re

_EEO = re.compile(r"regardless of|without regard|protected (class|veteran|status)|discriminat|equal (employment )?opportunity|"
                  r"e-?verify|affirmative action", re.I)

BLOCK = [
    (re.compile(r"\bu\.?\s?s\.?\s?citizen(s|ship)?\b|\bunited states citizen(s|ship)?\b", re.I),
     "Requires US citizenship"),
    (re.compile(r"\b(lawful )?permanent residen(t|ts|cy)\b|\bgreen card\b", re.I),
     "Requires permanent residency / green card"),
    (re.compile(r"authori[sz](ed|ation)[^.;\n]{0,80}\b(indefinite(ly)?|permanent(ly)?|on a permanent basis)\b|"
                r"\b(indefinite(ly)?|permanent(ly)?)\b[^.;\n]{0,60}\b(work[- ]?)?authori[sz](ed|ation)\b", re.I),
     "Requires permanent / indefinite work authorization"),
    (re.compile(r"\b(not|unable to|cannot|can't|do not|does not|don't|doesn't|won't|will not|no)\b[^.;\n]{0,60}"
                r"\b(OPT|CPT|F-?1|STEM OPT|student visas?|J-?1)\b|"
                r"\b(OPT|CPT|F-?1|STEM OPT|student visas?)\b[^.;\n]{0,50}\b(not (eligible|accepted|considered|supported)|"
                r"ineligible|excluded)\b", re.I),
     "Explicitly excludes OPT / CPT / F-1"),
    (re.compile(r"\b(security|secret|top secret|ts/sci) clearance\b|\bITAR\b|\bexport control(led|s)?\b[^.;\n]{0,60}"
                r"\bu\.?s\.? persons?\b|\bu\.?s\.? persons?\b[^.;\n]{0,40}\b(as defined|itar|export)", re.I),
     "Needs security clearance / ITAR US-person status"),
]
# Sentences that mention citizenship/green card but are actually GOOD for me
_POSITIVE = re.compile(r"\b(or|and)\b[^.;\n]{0,15}\b(any|other|valid|all)\b[^.;\n]{0,30}authori[sz]|"
                       r"\b(OPT|CPT|F-?1)\b[^.;\n]{0,25}\b(ok|okay|accepted|welcome|eligible|considered|encouraged)\b|"
                       r"\b(will|can|do|does|happy to)\s+sponsor\b|\bsponsorship\b[^.;\n]{0,15}\b(is )?(available|offered|provided)\b",
                       re.I)
_NEG = re.compile(r"\b(not|unable|cannot|can't|don't|doesn't|won't|no|never|without)\b", re.I)
NO_SPONSOR = re.compile(r"\b(not|unable to|cannot|can't|do not|does not|don't|doesn't|won't|will not|no|without)\b[^.;\n]{0,50}"
                        r"\bsponsor(ship|ing)?\b|\bsponsorship (is )?not (available|offered|provided)\b", re.I)


def _sentences(text: str) -> list[str]:
    # "U.S." must not end a sentence
    text = re.sub(r"\bU\.\s?S\.(\s?A\.)?", "US", text or "", flags=re.I)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+|•|;", text) if s.strip()]


def check(text: str) -> dict:
    """-> {verdict: dont_apply | apply | unknown, reason, quote}"""
    if not (text or "").strip():
        return {"verdict": "unknown", "reason": "No job description to check yet.", "quote": ""}
    note = None
    sents = _sentences(text)
    # also check each pair of neighbours: pasted postings often break one sentence across lines
    for s in sents + [f"{a} {b}" for a, b in zip(sents, sents[1:])]:
        if _EEO.search(s) or (_POSITIVE.search(s) and not _NEG.search(s)):
            continue
        for rx, reason in BLOCK:
            if rx.search(s):
                return {"verdict": "dont_apply", "reason": f"{reason}. Not eligible on a student visa, skip it.", "quote": s[:300]}
        if not note and NO_SPONSOR.search(s):
            note = {"verdict": "apply", "reason": "Says no sponsorship, but doesn't exclude OPT/CPT or require "
                                                  "citizenship. Still apply.", "quote": s[:300]}
    return note or {"verdict": "apply", "reason": "Nothing about citizenship or visas. Apply.", "quote": ""}
