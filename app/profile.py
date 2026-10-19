"""Loads my profile files. `profile/<name>.md` is the real one; `<name>.template.md` is the fallback.

The markdown files come from ai-job-application-kit's memory/ templates (MIT, see third_party/),
plus resume.md, voice.md and me.json which are specific to this app.
"""
import json
from pathlib import Path

from .db import ROOT

PROFILE_DIR = ROOT / "profile"

# name -> what it's for (shown in the Profile tab)
FILES = {
    "resume": "Master resume. Messy is fine: paste every resume version you have (analyst, PM, AI, ...), all of them.",
    "experience": "Narratives: the full story of what you did in each role. Tailoring reframes from this.",
    "voice": "How I write. Paste real messages that got replies.",
    "profile": "Headline, target roles, strong-fit domains, short summary.",
    "resume-preferences": "Formatting rules for tailored resumes.",
    "application-style": "How to answer 'why us' / free-text questions.",
    "sponsorship-filter": "Work-authorization filter rules.",
}


def playbook_names() -> list[str]:
    """profile/playbook-<family>.md: a fixed resume + rules for a role family (e.g. playbook-pm)."""
    return sorted(p.stem for p in PROFILE_DIR.glob("playbook-*.md"))


for _name in playbook_names():
    FILES.setdefault(_name, "Playbook: the fixed resume + rules for this role family. Tailoring follows it exactly.")

ME_DEFAULTS = {
    "name": "",
    "headline": "",
    "location": "",
    "linkedin_url": "",
    "school": "",
    "school_aliases": [],
    "grad_year": "",
    "past_employers": [],
    "programs": [],
    "hometown": "",
    "high_school": "",
    "target_roles": [],
    "avoid_roles": [],
    "grad_date_internship": "",   # expected graduation shown on internship applications
    "grad_date_full_time": "",    # expected graduation shown on new-grad / full-time applications
    "gpa": "",                    # shown ONLY when the JD mentions a GPA requirement, exactly as written
    # Two resume versions per job (my A/B strategy). Same real name/phone/facts; different angle + email.
    "variants": {
        "A": {"name": "", "email": "", "strategy": "Best-fit angle: the single strongest truthful pitch for this role family."},
        "B": {"name": "", "email": "", "strategy": "Alternate angle: the second-strongest truthful pitch, leading with different roles/projects than A."},
    },
    "single_version_companies": [],  # companies where I only send ONE version (they detect duplicates)
    "calendly_url": "",
    # Skills stretch: when the resume covers < below_match_pct of the JD's keywords, Skills may list adjacent /
    # quickly-learnable tools; each one goes on a learn-before-interview list.
    "skill_stretch": {"enabled": False, "below_match_pct": 80, "learn_within_days": 7},
    "company_certs": {},  # {"Robinhood": ["FinTech Industry Professional (FTIP®) Certification"]}: always "(in progress)" there
    "visa_status": "",            # e.g. "F-1 student (OPT/CPT)": turns on the can-I-apply check
    "connection_note_limit": 200,
    "weights": {"pastEmployer": 4, "program": 3, "university": 2, "hometown": 1},
}


def _path(name: str, ext: str = "md") -> Path:
    return PROFILE_DIR / f"{name}.{ext}"


def read(name: str) -> tuple[str, bool]:
    """Returns (text, is_real). is_real=False means we fell back to the blank template."""
    real = _path(name)
    if real.exists():
        return real.read_text(), True
    tpl = PROFILE_DIR / f"{name}.template.md"
    return (tpl.read_text() if tpl.exists() else ""), False


def write(name: str, text: str) -> None:
    if name not in FILES:
        raise ValueError(f"unknown profile file: {name}")
    PROFILE_DIR.mkdir(exist_ok=True)
    _path(name).write_text(text)


def me() -> dict:
    p = _path("me", "json")
    data = json.loads(p.read_text()) if p.exists() else {}
    merged = {**ME_DEFAULTS, **data}
    merged["weights"] = {**ME_DEFAULTS["weights"], **(data.get("weights") or {})}
    return merged


def save_me(data: dict) -> None:
    PROFILE_DIR.mkdir(exist_ok=True)
    _path("me", "json").write_text(json.dumps({**ME_DEFAULTS, **data}, indent=2))


def real_or_blank(name: str) -> str:
    """For prompts: only send files I've actually filled in, never the placeholder template."""
    text, is_real = read(name)
    return text if is_real else ""


def append_facts(facts: list[str], source: str) -> None:
    """New facts I told the resume chat -> my narratives file, so every future tailor knows them."""
    from datetime import date
    text, is_real = read("experience")
    base = text if is_real else ""
    header = "## Added from resume chats"
    if header not in base:
        base = base.rstrip() + f"\n\n{header}\n"
    lines = "\n".join(f"- {f}" for f in facts if f.strip())
    write("experience", base.rstrip() + f"\n\n_{date.today().isoformat()}, while tailoring for {source}:_\n{lines}\n")


TONE_HEADER = "## Tone corrections (I told it these; newest last)"
SENT_HEADER = "## Messages I actually sent (auto-saved, latest 15)"
SENT_KEEP = 15


def _split_voice() -> tuple[str, list[str], list[str]]:
    """voice.md -> (main text, tone notes, sent examples)."""
    text, is_real = read("voice")
    text = text if is_real else ""
    main, notes, sent = text, [], []
    if SENT_HEADER in main:
        main, rest = main.split(SENT_HEADER, 1)
        sent = [b.strip() for b in rest.split("\n---\n") if b.strip()]
    if TONE_HEADER in main:
        main, rest = main.split(TONE_HEADER, 1)
        notes = [l[2:].strip() for l in rest.splitlines() if l.startswith("- ")]
    return main.rstrip(), notes, sent


def _write_voice(main: str, notes: list[str], sent: list[str]) -> None:
    out = main + "\n"
    if notes:
        out += f"\n{TONE_HEADER}\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    if sent:
        out += f"\n{SENT_HEADER}\n" + "\n---\n".join(sent[-SENT_KEEP:]) + "\n"
    write("voice", out)


def add_tone_note(note: str) -> None:
    main, notes, sent = _split_voice()
    if note.strip() and note.strip() not in notes:
        notes.append(note.strip())
    _write_voice(main, notes, sent)


def remember_sent(message: str, context: str) -> None:
    """The final text I actually sent (after my edits) is the best voice example there is."""
    if len(message.strip()) < 20:
        return
    main, notes, sent = _split_voice()
    sent.append(f"[{context}]\n{message.strip()}")
    _write_voice(main, notes, sent)


def resume_versions() -> list[str]:
    """'## Version H: AI Product / PM' headings from my master resume, for the 'base on version' picker."""
    import re as _re
    text, is_real = read("resume")
    return _re.findall(r"^## (Version [A-Z][^\n]*)", text, _re.M) if is_real else []


def playbooks_block() -> str:
    parts = []
    for name in playbook_names():
        text, _ = read(name)
        parts.append(f"<PLAYBOOK {name}>\n{text.strip()}\n</PLAYBOOK {name}>")
    if not parts:
        return ""
    return ("ROLE-FAMILY PLAYBOOKS: if this JD's role matches a playbook's 'Applies to' list, FOLLOW THAT PLAYBOOK "
            "EXACTLY. It overrides the general reframing/selection rules (truthfulness, one page, no italics, grad date, "
            "GPA and identity rules still apply). In `changes`, say which playbook you used and what you changed.\n\n"
            + "\n\n".join(parts))


def languages() -> dict:
    """Extra outreach languages from profile/languages.json (private): {code: {label, instruction, name_pattern}}."""
    path = PROFILE_DIR / "languages.json"
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}
