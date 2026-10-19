"""Job OS: one local page for roles, people to message, messages, and tailored resumes.

Run: ./run.sh   (or: uvicorn app.main:app --reload)  ->  http://localhost:8000
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import re
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, db, importers, latex, linkedin, nextup, profile, sources, warmpaths, workauth
from .db import one, rows

app = FastAPI(title="Job OS")
# The Chrome side panel (extension/) talks to this server. Localhost only, just me.
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*|http://localhost(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])
STATIC = Path(__file__).parent / "static"
FOLLOW_UP_AFTER_DAYS = 4  # Recruiting OS escalation: tier 1 nudge starts at day 4

db.init()


@app.exception_handler(ai.AIError)
async def ai_error(_, exc: ai.AIError):
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": str(exc)}, status_code=400)


# ---- helpers ------------------------------------------------------------------------
VARIANTS = ("A", "B")
COL = {"A": "tailored_resume", "B": "tailored_resume_b"}
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _variant(v: str) -> str:
    v = (v or "A").upper()
    if v not in VARIANTS:
        raise HTTPException(400, "variant must be A or B")
    return v


def _single_version(job: dict, me: dict) -> bool:
    """Companies where I only send one version (they detect duplicates), e.g. Google, TikTok."""
    return any(warmpaths.same_company(job["company"], c) for c in me.get("single_version_companies") or [])


def _me_for(me: dict, v: str) -> dict:
    """My profile as this version presents it: the version's name (e.g. a preferred name vs. a legal name) drives
    the resume header and the PDF file name."""
    cfg = (me.get("variants") or {}).get(v, {})
    return {**me, "name": cfg.get("name") or me.get("name", "")}


# GitHub only for genuinely technical roles. Technical PM / product roles don't get it (my call).
TECHNICAL_ROLE = re.compile(r"\b(software|data|ml|machine learning|ai|backend|frontend|full[- ]?stack|platform|devops)\s+"
                            r"(engineer|developer)|\bdeveloper\b|data scien|research scientist|\bquant|artificial intelligence|"
                            r"\bAI\b[^,]{0,25}\b(analyst|engineer|developer)", re.I)
_GITHUB_IN_HEADER = re.compile(r"\s*\$\|\$\s*\\href\{https://github\.com/[A-Za-z0-9_-]+/?\}\{[^{}]*(\{[^{}]*\})?[^{}]*\}")


def _fit_header(tex: str, job: dict) -> str:
    """GitHub only on technical roles; keeps the contact line to one line."""
    if TECHNICAL_ROLE.search(job.get("role", "")):
        return tex
    return _GITHUB_IN_HEADER.sub("", tex, count=1)


def _house_style(tex: str) -> str:
    """My fixed formatting rules, applied in code so the AI can't drift: current template preamble + spacing,
    'Project' (singular) heading, Education spacing macro, bold stack names in bullets."""
    base = profile.PROFILE_DIR / "resume.tex"
    if base.exists() and "\\begin{document}" in tex:
        pre = base.read_text().partition("\\begin{document}")[0]
        body = tex.partition("\\begin{document}")[2]
        if "\\resumeItem" in pre:                       # only when it's my own template layout
            tex = pre + "\\begin{document}" + body.replace("\\vspace{\\jobosgap}", "")
    tex = tex.replace("\\section{Projects}", "\\section{Project}")
    tex = latex.fact_guard(tex)
    # Coursework/Certificates sit close under the degree line (New grad ratio)
    tex = tex.replace("\\vspace{-0.5pt}\\vspace{\\joboseduskip}\\textbf{Coursework:}", "\\vspace{-2pt}\\vspace{\\joboseduskip}\\textbf{Coursework:}")
    tex = tex.replace("\\vspace{-2.1pt}\\vspace{\\joboseduskip}\\textbf{Certificates:}", "\\vspace{-3.6pt}\\vspace{\\joboseduskip}\\textbf{Certificates:}")
    if "\\joboseduskip" in tex.partition("\\begin{document}")[0]:
        tex = re.sub(r"(\\vspace\{-?[\d.]+pt\})(?!\\vspace\{\\joboseduskip\})(\\textbf\{(?:Relevant )?(?:Coursework|Certificates):?)",
                     r"\1\\vspace{\\joboseduskip}\2", tex)
    m = re.search(r"\\section\{Education\}", tex)
    if m and "\\resumeEduHeading" in tex.partition("\\begin{document}")[0]:
        j = tex.find("\\resumeSubheading", m.end())
        k = tex.find("\\section{", m.end())
        if j != -1 and (k == -1 or j < k):
            tex = tex[:j] + "\\resumeEduHeading" + tex[j + len("\\resumeSubheading"):]
    tex = re.sub(r"(\\href\{https://www\.linkedin\.com/[^\n]*\n(?:[^\n]*github[^\n]*\n)?)\s*\\vspace\{-?\d+(\.\d+)?pt\}\s*\n\\end\{center\}",
                 lambda mm: mm.group(1) + "    \\vspace{0pt}\n\\end{center}", tex)
    # breathing room between the Skills heading line and the first skills line
    tex = re.sub(r"(\\section\{Skills\}\s*\n)\s*\\vspace\{-?[\d.]+pt\}", r"\1\\vspace{2pt}", tex)
    # my rule: bold key numbers + key tech inside bullets; never bold the GPA
    return latex.keep_together(latex.unbold_gpa(latex.bold_numbers(latex.bold_stack(latex.normalize_spacing(tex)))))


def _set_identity(tex: str, me: dict, v: str) -> str:
    """Deterministic: whatever the model wrote, the header gets this version's name and email."""
    cfg = (me.get("variants") or {}).get(v, {})
    if cfg.get("email"):
        tex = _EMAIL_RE.sub(cfg["email"], tex)
    base, name = me.get("name", ""), cfg.get("name", "")
    if base and name and name != base:
        tex = tex.replace(base, name)
    return tex


def _variant_info(job: dict, me: dict) -> dict:
    out = {}
    for v in VARIANTS:
        pdf = latex.pdf_for(job, _me_for(me, v), v)
        out[v] = {"pdf_url": f"/api/jobs/{job['id']}/resume.pdf?variant={v}" if pdf else None,
                  "name": _me_for(me, v)["name"], "filename": latex.filename(_me_for(me, v), job["company"]),
                  "email": (me.get("variants") or {}).get(v, {}).get("email", ""),
                  "has_tex": bool(job.get(COL[v])),
                  "score": resume_score(job.get(COL[v]) or "", _keywords(job))}
    return out


def _norm_kw(s: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", s.lower()).strip()


def resume_score(tex: str, keywords: list[str]) -> dict | None:
    """ATS-style match: share of the JD's must-have keywords that appear in the resume text."""
    if not tex or not keywords:
        return None
    text = " " + _norm_kw(latex.plain_text(tex)) + " "
    matched, missing = [], []
    for k in keywords:
        nk = _norm_kw(k)
        (matched if nk and f" {nk} " in text else missing).append(k)
    return {"score": round(100 * len(matched) / len(keywords)), "matched": matched, "missing": missing}


def _save_stretch(job_id: int, skills: list[str]) -> None:
    """Merge into the job's learn-before-interview list."""
    if not skills:
        return
    with db.session() as conn:
        row = one(conn.execute("SELECT stretch_skills FROM jobs WHERE id = ?", (job_id,)))
        have = json.loads(row["stretch_skills"] or "[]") if row else []
        merged = have + [x for x in skills if x not in have]
        conn.execute("UPDATE jobs SET stretch_skills = ? WHERE id = ?", (json.dumps(merged), job_id))


def _keywords(job: dict) -> list[str]:
    try:
        return json.loads(job.get("fit_notes") or "{}").get("jd_keywords") or json.loads(job.get("jd_keywords") or "[]")
    except ValueError:
        return []


def _work_auth(text: str, me: dict, fit_notes: str = "") -> dict | None:
    """Instant phrase check, backed up by the AI fit check (it reads nuance the phrases miss)."""
    if not me.get("visa_status"):
        return None
    r = workauth.check(text)
    if r["verdict"] != "dont_apply" and fit_notes:
        try:
            verdict = json.loads(fit_notes).get("verdict", "")
        except ValueError:
            verdict = ""
        if verdict.lower().startswith("not eligible"):
            return {"verdict": "dont_apply", "reason": "Fit check: " + verdict.split(".")[0] + ".", "quote": ""}
    return r


def _job_or_404(conn, job_id: int) -> dict:
    job = one(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)))
    if not job:
        raise HTTPException(404, "job not found")
    return job


def _interaction_counts(conn) -> dict[int, int]:
    return {r["person_id"]: r["n"] for r in conn.execute(
        "SELECT person_id, count(*) AS n FROM interactions GROUP BY person_id")}


def _people_for_job(conn, job: dict, me: dict) -> list[dict]:
    """Everyone at the company (ranked) + anyone I manually attached to this job."""
    people = rows(conn.execute("SELECT * FROM people"))
    counts = _interaction_counts(conn)
    ranked = warmpaths.rank_for_job(job, people, me, counts)
    links = {r["person_id"]: r for r in rows(conn.execute("SELECT * FROM job_people WHERE job_id = ?", (job["id"],)))}
    seen = {p["id"] for p in ranked}
    for pid in links:
        if pid not in seen:
            p = one(conn.execute("SELECT * FROM people WHERE id = ?", (pid,)))
            if p:
                ranked.append({**p, **warmpaths.score_person(p, job, me, counts.get(pid, 0))})
    for p in ranked:
        link = links.get(p["id"])
        p["link"] = link  # None = suggested only
    ranked.sort(key=lambda p: (p["link"] is None, -p["score"]))
    return ranked


def url_key(url: str) -> str:
    """Same job, different URL shapes -> same key. LinkedIn search pages carry the job in ?currentJobId=,
    company career sites often use Greenhouse's ?gh_jid=."""
    if not url:
        return ""
    u = urlparse(url if "//" in url else f"https://{url}")
    q = parse_qs(u.query)
    host = u.netloc.lower().removeprefix("www.")
    if "linkedin.com" in host and q.get("currentJobId"):
        return f"linkedin.com/jobs/view/{q['currentJobId'][0]}"
    if q.get("gh_jid"):
        return f"{host}?gh_jid={q['gh_jid'][0]}"
    path = u.path.rstrip("/")
    path = path.removesuffix("/application").removesuffix("/apply")
    return f"{host}{path}".lower()


# ---- pages --------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/meta")
def meta():
    files = {}
    for name, desc in profile.FILES.items():
        _, is_real = profile.read(name)
        files[name] = {"description": desc, "filled": is_real}
    with db.session() as conn:
        n_people = conn.execute("SELECT count(*) FROM people").fetchone()[0]
    return {"statuses": db.STATUSES, "contact_statuses": db.CONTACT_STATUSES, "message_kinds": list(ai.KINDS),
            "profile_files": files, "me": profile.me(), "people_count": n_people, "model": ai.MODEL,
            "resume_versions": profile.resume_versions()}


# ---- jobs ---------------------------------------------------------------------------
class TextIn(BaseModel):
    text: str


class JobIn(BaseModel):
    company: str
    role: str
    url: str = ""
    location: str = ""
    jd: str = ""
    priority: int = 2


class JobPatch(BaseModel):
    company: str | None = None
    role: str | None = None
    url: str | None = None
    location: str | None = None
    jd: str | None = None
    status: str | None = None
    priority: int | None = None
    notes: str | None = None
    tailored_resume: str | None = None
    company_linkedin_id: str | None = None
    follow_up_on: str | None = None
    applied_on: str | None = None
    response_variant: str | None = None


@app.get("/api/jobs")
def list_jobs():
    me = profile.me()
    with db.session() as conn:
        jobs = rows(conn.execute("SELECT * FROM jobs ORDER BY status IN ('rejected','archived'), priority, updated_at DESC"))
        people = rows(conn.execute("SELECT * FROM people"))
        counts = _interaction_counts(conn)
        links = rows(conn.execute("SELECT jp.*, p.name FROM job_people jp JOIN people p ON p.id = jp.person_id"))
    for j in jobs:
        ranked = warmpaths.rank_for_job(j, people, me, counts)
        mine = [l for l in links if l["job_id"] == j["id"]]
        j["coverage"] = "strong" if any(l["status"] in ("replied", "referred") for l in mine) else warmpaths.coverage(ranked)
        j["warm_count"] = len(ranked)
        j["best_person"] = ranked[0]["name"] if ranked else None
        j["contacted"] = sum(l["status"] not in ("suggested", "to_contact") for l in mine)
        j["replied"] = sum(l["status"] in ("replied", "referred") for l in mine)
        j["work_auth"] = _work_auth(j["jd"], me, j["fit_notes"])
        j.pop("jd", None)
        j.pop("tailored_resume", None)
        j.pop("tailored_resume_b", None)
    return jobs


@app.post("/api/jobs")
def create_job(job: JobIn):
    key = url_key(job.url.strip())
    with db.session() as conn:
        if key:
            dup = one(conn.execute("SELECT id FROM jobs WHERE url_key = ?", (key,)))
            if dup:
                return {"id": dup["id"], "existing": True}
        cur = conn.execute("INSERT INTO jobs (company, role, url, url_key, location, jd, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (job.company.strip(), job.role.strip(), job.url.strip(), key, job.location.strip(), job.jd, job.priority))
        return {"id": cur.lastrowid}


class PasteIn(BaseModel):
    text: str
    url: str = ""


@app.post("/api/jobs/from-paste")
def create_from_paste(body: PasteIn):
    """Paste the whole posting; Claude pulls out company / role / location."""
    f = ai.extract_job(body.text)
    return create_job(JobIn(company=f["company"] or "?", role=f["role"] or "?", url=body.url or f["url"],
                            location=f["location"], jd=f["jd"] or body.text))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        people = _people_for_job(conn, job, me)
        log = rows(conn.execute(
            """SELECT i.*, p.name FROM interactions i LEFT JOIN people p ON p.id = i.person_id
               WHERE i.job_id = ? ORDER BY i.created_at DESC""", (job_id,)))
    job["fit"] = json.loads(job["fit_notes"]) if job["fit_notes"] else None
    job["stretch_skills"] = json.loads(job.get("stretch_skills") or "[]")
    job["work_auth"] = _work_auth(job["jd"], me, job["fit_notes"])
    variants = _variant_info(job, me)
    return {"job": job, "people": people, "searches": linkedin.people_searches(job, me), "log": log,
            "pdf_url": variants["A"]["pdf_url"], "filename": latex.filename(me, job["company"]),
            "variants": variants, "single_version": _single_version(job, me)}


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: int, patch: JobPatch):
    fields = patch.model_dump(exclude_none=True)
    if "status" in fields and fields["status"] not in db.STATUSES:
        raise HTTPException(400, "bad status")
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        if fields.get("status") == "applied" and not job["applied_on"]:
            fields["applied_on"] = date.today().isoformat()
        if not fields:
            return job
        if "url" in fields:
            fields["url_key"] = url_key(fields["url"])
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE jobs SET {sets}, updated_at = datetime('now') WHERE id = ?", (*fields.values(), job_id))
        return _job_or_404(conn, job_id)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    with db.session() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/fit")
def job_fit(job_id: int):
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    result = ai.fit_check(job)
    with db.session() as conn:
        conn.execute("UPDATE jobs SET fit_score = ?, fit_notes = ?, updated_at = datetime('now') WHERE id = ?",
                     (result["score"], json.dumps(result), job_id))
    return result


def _note(v: str, me: dict) -> str:
    cfg = (me.get("variants") or {}).get(v, {})
    return ai.variant_note(v, cfg.get("strategy", ""), cfg.get("email", ""))


FIT_ATTEMPTS = 5  # one item per attempt, so it never over-cuts
FILL_PASSES = 2


FILL_PAGE_MIN_LINES = 2


def _fill_page(tex: str, built: dict, job: dict, me: dict, v: str) -> tuple[str, dict, list[str]]:
    """No big empty space at the bottom: add the strongest relevant content, keep it only if still one page."""
    added = []
    for _ in range(2):
        try:
            free = latex.free_lines(built["pdf"])
        except Exception:
            break
        if free < FILL_PAGE_MIN_LINES:
            break
        r = ai.add_content(tex, free, job)
        new_tex = _fit_header(_set_identity(r["tex"], me, v), job)
        new_built = latex.compile_tex(new_tex, job, _me_for(me, v), v)
        if new_built["error"] or new_built["pages"] != 1 or latex.free_lines(new_built["pdf"]) >= free:
            latex.compile_tex(tex, job, _me_for(me, v), v)  # too much or no gain: restore
            break
        tex, built = new_tex, new_built
        added += [f"Added: {a}" for a in r["added"]]
    return tex, built, added


def _fill_lines(tex: str, built: dict, job: dict, me: dict, v: str) -> tuple[str, dict, list[str]]:
    """No white space on the right: measure the PDF, fix short-ending lines, keep a pass only if it helps."""
    changed = []
    try:
        issues = latex.short_lines(built["pdf"])
    except Exception:
        return tex, built, changed
    for _ in range(FILL_PASSES):
        if not issues:
            break
        r = ai.fill_lines(tex, issues, job)
        new_tex = _fit_header(_set_identity(r["tex"], me, v), job)
        new_built = latex.compile_tex(new_tex, job, _me_for(me, v), v)
        new_issues = latex.short_lines(new_built["pdf"]) if new_built["pdf"] and new_built["pages"] == 1 else None
        if new_issues is None or len(new_issues) >= len(issues):
            latex.compile_tex(tex, job, _me_for(me, v), v)  # restore the better PDF
            break
        tex, built, issues = new_tex, new_built, new_issues
        changed += r["changed"]
    return tex, built, changed


def _save_tex(job: dict, me: dict, v: str, tex: str, auto_fit: bool = True) -> dict:
    """Compile; if it's over one page, have Claude cut the lowest-scoring content and rebuild (up to 3 tries).
    auto_fit=False for my own hand edits: never rewrite what I typed."""
    tex = _house_style(_fit_header(_set_identity(tex, me, v), job))
    built = latex.compile_tex(tex, job, _me_for(me, v), v)
    if auto_fit and not built["error"] and built["pages"] > 1:
        tex, built = latex.stretch_to_fill(tex, job, _me_for(me, v), v)  # a slight overflow: tighten spacing first
    cuts = []
    for attempt in range(1, FIT_ATTEMPTS + 1):
        if not auto_fit or built["error"] or built["pages"] <= 1:
            break
        r = ai.fit_one_page(tex, built["pages"], job, attempt)
        tex = _fit_header(_set_identity(r["tex"], me, v), job)
        cuts += r["cut"]
        built = latex.compile_tex(tex, job, _me_for(me, v), v)
    filled = []
    if auto_fit and not built["error"] and built["pages"] == 1:
        tex, built, filled = _fill_page(tex, built, job, me, v)
        tex, built, more = _fill_lines(tex, built, job, me, v)
        filled += more
        tex, built = latex.stretch_to_fill(tex, job, _me_for(me, v), v)  # end exactly at the bottom
        tex, built = latex.equalize_section_gaps(tex, job, _me_for(me, v), v)  # same gap above every heading
    with db.session() as conn:
        conn.execute(
            f"""UPDATE jobs SET {COL[v]} = ?, status = CASE WHEN status = 'saved' THEN 'tailoring' ELSE status END,
                updated_at = datetime('now') WHERE id = ?""", (tex, job["id"]))
    return {**_pdf_info(job, _me_for(me, v), built, v), "cut_to_fit": cuts, "filled_lines": filled,
            "score": resume_score(tex, _keywords(job))}


@app.post("/api/jobs/{job_id}/tailor")
def job_tailor(job_id: int, variant: str = "A"):
    """Tailor -> .tex -> PDF named like Your_Name_Resume_Company.pdf, ready to drop into Simplify.
    variant=B makes my second version: different angle + second email."""
    v = _variant(variant)
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    if v == "B" and _single_version(job, me):
        raise HTTPException(400, f"{job['company']} is on your one-version list (they detect duplicates). Send version A only.")
    own_tex = profile.PROFILE_DIR / "resume.tex"
    if own_tex.exists() and ai.WRITER == "openai":
        # language work on OpenAI, then Claude puts it into my LaTeX layout
        result = ai.tailor_resume(job, _note(v, me))
        tex = ai.content_to_tex(own_tex.read_text(), result.pop("resume"), job)["tex"]
    elif own_tex.exists():
        result = ai.tailor_own_tex(job, own_tex.read_text(), _note(v, me))
        tex = result.pop("tex")
    else:
        result = ai.tailor_resume(job, _note(v, me))
        tex = latex.render(result.pop("resume"))
    if result.get("jd_keywords"):
        with db.session() as conn:
            conn.execute("UPDATE jobs SET jd_keywords = ? WHERE id = ? AND jd_keywords = ''",
                         (json.dumps(result["jd_keywords"]), job_id))
        job = {**job, "jd_keywords": job.get("jd_keywords") or json.dumps(result["jd_keywords"])}
    out = _save_tex(job, me, v, tex)
    certs = list(dict.fromkeys((result.get("certs_to_start") or []) + ai.company_certs(job)))
    _save_stretch(job_id, (result.get("stretch_skills") or []) + [f"{c} (start before you submit)" for c in certs])
    return {**result, **out, "variant": v}


def _pdf_info(job: dict, me: dict, built: dict, v: str = "A") -> dict:
    warn = built["error"] or ("" if built["pages"] <= 1 else f"PDF is {built['pages']} pages. Trim a bullet or two in the .tex.")
    return {"pdf_url": f"/api/jobs/{job['id']}/resume.pdf?variant={v}" if built["pdf"] else None,
            "filename": latex.filename(me, job["company"]), "pages": built["pages"], "warning": warn}


@app.post("/api/jobs/{job_id}/recompile")
def job_recompile(job_id: int, body: TextIn, variant: str = "A"):
    """After hand-editing the .tex in the app."""
    v = _variant(variant)
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    return _save_tex(job, me, v, body.text, auto_fit=False)


@app.get("/api/jobs/{job_id}/resume.pdf")
def job_resume_pdf(job_id: int, download: bool = False, variant: str = "A"):
    v = _variant(variant)
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    pdf = latex.pdf_for(job, _me_for(me, v), v)
    if not pdf:
        raise HTTPException(404, "No PDF yet. Tailor first.")
    return FileResponse(pdf, media_type="application/pdf", filename=pdf.name,
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/jobs/{job_id}/resume.tex")
def job_resume_tex(job_id: int, variant: str = "A"):
    v = _variant(variant)
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    return PlainTextResponse(job[COL[v]] or "", headers={
        "Content-Disposition": f'attachment; filename="{latex.filename(_me_for(me, v), job["company"])[:-4]}.tex"'})


# ---- people on a job ------------------------------------------------------------------
class PersonIn(BaseModel):
    name: str
    title: str = ""
    linkedin_url: str = ""
    relationship: str = ""
    notes: str = ""
    degree: int | None = None


@app.post("/api/jobs/{job_id}/people")
def add_person_to_job(job_id: int, p: PersonIn):
    """For people I found via the search links: paste name + title + URL."""
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        existing = one(conn.execute("SELECT id FROM people WHERE linkedin_url != '' AND linkedin_url = ?", (p.linkedin_url.strip(),)))
        if existing:
            pid = existing["id"]
        else:
            pid = conn.execute(
                """INSERT INTO people (name, company, title, linkedin_url, relationship, notes, degree, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')""",
                (p.name.strip(), job["company"], p.title.strip(), p.linkedin_url.strip(), p.relationship, p.notes, p.degree),
            ).lastrowid
        conn.execute("INSERT OR IGNORE INTO job_people (job_id, person_id) VALUES (?, ?)", (job_id, pid))
    return {"id": pid}


class LinkPatch(BaseModel):
    status: str
    message: str = ""
    follow_up_on: str | None = None


@app.put("/api/jobs/{job_id}/people/{person_id}")
def set_contact_status(job_id: int, person_id: int, body: LinkPatch):
    if body.status not in db.CONTACT_STATUSES:
        raise HTTPException(400, "bad status")
    today = date.today()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        conn.execute("INSERT OR IGNORE INTO job_people (job_id, person_id) VALUES (?, ?)", (job_id, person_id))
        fields = {"status": body.status}
        if body.status == "messaged":
            fields["messaged_on"] = today.isoformat()
            fields["follow_up_on"] = body.follow_up_on or (today + timedelta(days=FOLLOW_UP_AFTER_DAYS)).isoformat()
            if body.message:
                fields["last_message"] = body.message
            conn.execute("INSERT INTO interactions (person_id, job_id, kind, body) VALUES (?, ?, 'message', ?)",
                         (person_id, job_id, body.message))
            if body.message:
                profile.remember_sent(body.message, f"DM for {job['role']} @ {job['company']}")
            if job["status"] == "applied":
                conn.execute("UPDATE jobs SET status = 'reached_out', updated_at = datetime('now') WHERE id = ?", (job_id,))
        elif body.status in ("replied", "referred"):
            fields["follow_up_on"] = None
            conn.execute("INSERT INTO interactions (person_id, job_id, kind, body) VALUES (?, ?, ?, ?)",
                         (person_id, job_id, "referral" if body.status == "referred" else "reply", body.message))
        elif body.status == "no_reply":
            fields["follow_up_on"] = None
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE job_people SET {sets} WHERE job_id = ? AND person_id = ?", (*fields.values(), job_id, person_id))
    return {"ok": True}


class DraftIn(BaseModel):
    kind: str
    personalization: str = ""
    tier: int = 1
    language: str = "en"      # "en" or a code from profile/languages.json
    not_open: bool = False    # role isn't posted yet: networking early


@app.get("/api/languages")
def list_languages():
    """English plus any outreach languages defined in the private profile."""
    extra = [{"code": k, "label": v.get("label", k), "name_pattern": v.get("name_pattern", "")}
             for k, v in profile.languages().items()]
    return [{"code": "en", "label": "English", "name_pattern": ""}] + extra


@app.post("/api/jobs/{job_id}/people/{person_id}/draft")
def draft(job_id: int, person_id: int, body: DraftIn):
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        person = next((p for p in _people_for_job(conn, job, me) if p["id"] == person_id), None)
        if not person:
            person = one(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)))
        if not person:
            raise HTTPException(404, "person not found")
    previous = (person.get("link") or {}).get("last_message", "") if isinstance(person.get("link"), dict) else ""
    return ai.draft_message(job, person, body.kind, body.personalization, body.tier, previous,
                            body.language, body.not_open)


# ---- people / imports -----------------------------------------------------------------
@app.get("/api/people")
def search_people(q: str = ""):
    like = f"%{q.strip()}%"
    with db.session() as conn:
        return rows(conn.execute(
            """SELECT * FROM people WHERE name LIKE ? OR company LIKE ? OR title LIKE ?
               ORDER BY source = 'referral_sheet' DESC, name LIMIT 200""", (like, like, like)))


@app.post("/api/import/{source}")
async def import_csv(source: str, file: UploadFile = File(...)):
    if source not in ("connections", "referral_sheet"):
        raise HTTPException(400, "source must be connections or referral_sheet")
    text = (await file.read()).decode("utf-8", errors="replace")
    people = importers.parse(text, source)
    if not people:
        raise HTTPException(400, "Couldn't find any people in that CSV. Is it LinkedIn's Connections.csv?")
    with db.session() as conn:
        return importers.upsert_people(conn, people)


# ---- profile --------------------------------------------------------------------------

@app.get("/api/profile/{name}")
def get_profile(name: str):
    if name not in profile.FILES:
        raise HTTPException(404)
    text, is_real = profile.read(name)
    return {"name": name, "text": text, "filled": is_real}


@app.put("/api/profile/{name}")
def put_profile(name: str, body: TextIn):
    if name not in profile.FILES:
        raise HTTPException(404)
    profile.write(name, body.text)
    return {"ok": True}


@app.put("/api/me")
def put_me(body: dict):
    profile.save_me(body)
    return profile.me()


# ---- next up + role search ------------------------------------------------------------
@app.get("/api/nextup")
def get_nextup():
    with db.session() as conn:
        return nextup.queue(conn)


@app.get("/api/role-searches")
def role_searches():
    """SnipeDin-style LinkedIn job searches for each of my target roles, newest first."""
    me = profile.me()
    out = []
    for role in me.get("target_roles") or []:
        out.append({"label": f"{role} · past 24h", "url": linkedin.job_search_url(role, me.get("location", ""), "24h", True)})
        out.append({"label": f"{role} · remote, past week", "url": linkedin.job_search_url(role, "", "week", True, ["remote"])})
    return out


# ---- batch connection notes -------------------------------------------------------------
@app.post("/api/jobs/{job_id}/batch-notes")
def batch_notes(job_id: int, limit: int = 8):
    """Connection notes for the top people I'm not connected to yet, in one go."""
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        people = [p for p in _people_for_job(conn, job, me)
                  if p.get("degree") != 1 and (p["link"] or {}).get("status", "suggested") in ("suggested", "to_contact")]
    people = people[:limit]
    if not people:
        return []
    notes = {n["id"]: n for n in ai.batch_connection_notes(job, people)}
    return [{"person": p, **notes.get(p["id"], {"note": "", "over_limit": False})} for p in people]


# ---- browser side panel: auto-tracking ---------------------------------------------------
class PageIn(BaseModel):
    url: str
    title: str = ""
    text: str = ""


@app.post("/api/page/job")
def page_job(page: PageIn):
    """Side panel asks: is this page a job I'm tracking?"""
    key = url_key(page.url)
    with db.session() as conn:
        job = one(conn.execute("SELECT * FROM jobs WHERE url_key = ?", (key,))) if key else None
    if not job:
        return {"job": None}
    me = profile.me()
    variants = _variant_info(job, me)
    job["work_auth"] = _work_auth(job["jd"], me, job["fit_notes"])
    for k in ("jd", "tailored_resume", "tailored_resume_b"):
        job.pop(k, None)
    return {"job": job, "has_resume": variants["A"]["has_tex"], "pdf_url": variants["A"]["pdf_url"],
            "filename": latex.filename(me, job["company"]), "variants": variants}


@app.post("/api/page/save-job")
def page_save_job(page: PageIn):
    """One click on a job page: Claude reads the page text, saves the job (no pasting)."""
    key = url_key(page.url)
    with db.session() as conn:
        dup = one(conn.execute("SELECT id FROM jobs WHERE url_key = ?", (key,))) if key else None
    if dup:
        return {"id": dup["id"], "existing": True}
    f = ai.extract_job(f"Page title: {page.title}\n\n{page.text[:30000]}")
    return create_job(JobIn(company=f["company"] or "?", role=f["role"] or page.title or "?", url=page.url,
                            location=f["location"], jd=f["jd"] or page.text[:30000]))


class AppliedIn(BaseModel):
    job_id: int | None = None
    url: str = ""
    variants: list[str] = []  # which versions I sent; empty = don't change the record


@app.post("/api/track/applied")
def track_applied(body: AppliedIn):
    """Called when the side panel sees a 'thanks for applying' page, or I click 'I applied'."""
    with db.session() as conn:
        job = None
        if body.job_id:
            job = one(conn.execute("SELECT * FROM jobs WHERE id = ?", (body.job_id,)))
        if not job and body.url:
            job = one(conn.execute("SELECT * FROM jobs WHERE url_key = ?", (url_key(body.url),)))
        if not job:
            raise HTTPException(404, "Couldn't tell which job this was")
        if job["status"] in ("saved", "tailoring"):
            conn.execute("UPDATE jobs SET status = 'applied', applied_on = date('now'), updated_at = datetime('now') WHERE id = ?",
                         (job["id"],))
        if body.variants:
            sent = set(filter(None, (job["applied_variants"] or "").split(","))) | {_variant(v) for v in body.variants}
            conn.execute("UPDATE jobs SET applied_variants = ? WHERE id = ?", (",".join(sorted(sent)), job["id"]))
    return {"id": job["id"], "company": job["company"], "role": job["role"]}


@app.get("/api/ab-stats")
def ab_stats():
    """Which version gets more replies? Counts jobs where I sent each version and marked which one got a response."""
    with db.session() as conn:
        jobs = rows(conn.execute("SELECT applied_variants, response_variant FROM jobs WHERE applied_variants != ''"))
    out = {}
    for v in VARIANTS:
        sent = [j for j in jobs if v in j["applied_variants"].split(",")]
        replies = [j for j in sent if j["response_variant"] in (v, "both")]
        out[v] = {"sent": len(sent), "replies": len(replies),
                  "rate": round(100 * len(replies) / len(sent)) if sent else None}
    return out


def _profile_url(url: str) -> str:
    """https://www.linkedin.com/in/jane-doe-123/?foo -> https://www.linkedin.com/in/jane-doe-123"""
    u = urlparse(url)
    parts = [p for p in u.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "in":
        return f"https://www.linkedin.com/in/{parts[1]}"
    return url.split("?")[0].rstrip("/")


@app.post("/api/page/person")
def page_person(page: PageIn):
    """Side panel on a LinkedIn profile: who is this, and which of my jobs are they useful for?"""
    purl = _profile_url(page.url)
    me = profile.me()
    with db.session() as conn:
        person = one(conn.execute("SELECT * FROM people WHERE linkedin_url = ?", (purl,)))
    fields = ai.extract_person(page.text, purl) if page.text else None
    with db.session() as conn:
        if fields and fields.get("name"):
            rel = "; ".join(x for x in [
                f"school: {fields['school']}" if fields.get("school") else "",
                f"past: {', '.join(fields['past_companies'])}" if fields.get("past_companies") else "",
                fields.get("shared") or ""] if x)
            degree = fields.get("degree") or None
            if person:
                conn.execute(
                    """UPDATE people SET name = ?, company = COALESCE(NULLIF(?, ''), company), title = COALESCE(NULLIF(?, ''), title),
                       degree = COALESCE(?, degree), relationship = CASE WHEN relationship = '' THEN ? ELSE relationship END
                       WHERE id = ?""",
                    (fields["name"], fields["company"], fields["title"] or fields["headline"], degree, rel, person["id"]))
            else:
                conn.execute(
                    """INSERT INTO people (name, company, title, linkedin_url, source, degree, relationship)
                       VALUES (?, ?, ?, ?, 'browser', ?, ?)""",
                    (fields["name"], fields["company"], fields["title"] or fields["headline"], purl, degree, rel))
            person = one(conn.execute("SELECT * FROM people WHERE linkedin_url = ?", (purl,)))
        if not person:
            return {"person": None, "jobs": []}

        # They accepted my request? Move them along so Next Up says "send your pitch".
        if person.get("degree") == 1:
            conn.execute("UPDATE job_people SET status = 'connected' WHERE person_id = ? AND status = 'requested'", (person["id"],))

        counts = _interaction_counts(conn)
        jobs = rows(conn.execute("SELECT * FROM jobs WHERE status NOT IN ('rejected', 'archived') ORDER BY updated_at DESC"))
        out = []
        for j in jobs:
            link = one(conn.execute("SELECT * FROM job_people WHERE job_id = ? AND person_id = ?", (j["id"], person["id"])))
            if not link and not warmpaths.same_company(person.get("company", ""), j["company"]):
                continue
            sc = warmpaths.score_person(person, j, me, counts.get(person["id"], 0))
            out.append({"job": {k: j[k] for k in ("id", "company", "role", "status", "url")}, "link": link, **sc})
    return {"person": person, "jobs": out}


class OutreachIn(BaseModel):
    linkedin_url: str
    job_id: int | None = None
    kind: str  # requested | messaged
    message: str = ""


@app.post("/api/track/outreach")
def track_outreach(body: OutreachIn):
    """Logged automatically when I click Send / Connect on LinkedIn, or with one click in the panel."""
    if body.kind not in ("requested", "messaged"):
        raise HTTPException(400, "kind must be requested or messaged")
    purl = _profile_url(body.linkedin_url)
    with db.session() as conn:
        person = one(conn.execute("SELECT * FROM people WHERE linkedin_url = ?", (purl,)))
        if not person:
            raise HTTPException(404, "Open their profile with the side panel first so I know who they are")
        job_id = body.job_id
        if not job_id:
            for j in rows(conn.execute("SELECT * FROM jobs WHERE status NOT IN ('rejected','archived') ORDER BY updated_at DESC")):
                if warmpaths.same_company(person["company"], j["company"]):
                    job_id = j["id"]
                    break
    if not job_id:
        return {"ok": False, "reason": f"No tracked job at {person['company'] or 'their company'}"}
    if body.kind == "messaged":
        set_contact_status(job_id, person["id"], LinkPatch(status="messaged", message=body.message))
    else:
        with db.session() as conn:
            conn.execute("INSERT OR IGNORE INTO job_people (job_id, person_id) VALUES (?, ?)", (job_id, person["id"]))
            conn.execute("UPDATE job_people SET status = 'requested', last_message = ?, messaged_on = date('now') "
                         "WHERE job_id = ? AND person_id = ? AND status IN ('suggested', 'to_contact')",
                         (body.message, job_id, person["id"]))
            conn.execute("INSERT INTO interactions (person_id, job_id, kind, body) VALUES (?, ?, 'connection_request', ?)",
                         (person["id"], job_id, body.message))
        if body.message:
            profile.remember_sent(body.message, f"connection note for {person['company'] or 'a company'}")
    return {"ok": True, "job_id": job_id, "person": person["name"]}


# ---- resume chat --------------------------------------------------------------------------
class ChatIn(BaseModel):
    message: str = ""
    variant: str = "A"


@app.get("/api/jobs/{job_id}/resume-chat")
def get_resume_chat(job_id: int):
    with db.session() as conn:
        return rows(conn.execute("SELECT role, content, created_at FROM resume_chat WHERE job_id = ? ORDER BY id", (job_id,)))


@app.post("/api/jobs/{job_id}/resume-chat")
def post_resume_chat(job_id: int, body: ChatIn):
    """Chat with a resume coach about this job: it asks gap questions, I answer or give instructions,
    it rebuilds the PDF."""
    me = profile.me()
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
        transcript = rows(conn.execute("SELECT role, content FROM resume_chat WHERE job_id = ? ORDER BY id", (job_id,)))
    v = _variant(body.variant)
    own_tex_path = profile.PROFILE_DIR / "resume.tex"
    own_tex = own_tex_path.exists()
    current = job[COL[v]] or (own_tex_path.read_text() if own_tex else "")
    r = ai.resume_chat(job, transcript, body.message, current, own_tex, _note(v, me))

    pdf = {}
    if r["update_resume"]:
        if r.get("tex"):
            tex = r["tex"]
        elif own_tex:  # OpenAI wrote structured content; Claude turns it into my LaTeX layout
            tex = ai.content_to_tex(own_tex_path.read_text(), r["resume"], job)["tex"]
        else:
            tex = latex.render(r["resume"])
        pdf = _save_tex(job, me, v, tex)
        _save_stretch(job_id, (r.get("stretch_skills") or [])
                      + [f"{c} (start before you submit)" for c in r.get("certs_to_start") or []])
    reply = r["reply"] + ("\n\n" + "\n".join(f"• {q}" for q in r["questions"]) if r["questions"] and not
                          all(q in r["reply"] for q in r["questions"]) else "")
    with db.session() as conn:
        if body.message.strip():
            conn.execute("INSERT INTO resume_chat (job_id, role, content) VALUES (?, 'me', ?)", (job_id, body.message.strip()))
        conn.execute("INSERT INTO resume_chat (job_id, role, content) VALUES (?, 'claude', ?)", (job_id, reply))
    return {"reply": reply, "new_facts": r["new_facts"], "updated": r["update_resume"], "changes": r["changes"], **pdf}


class FactsIn(BaseModel):
    facts: list[str]


@app.post("/api/jobs/{job_id}/save-facts")
def save_facts(job_id: int, body: FactsIn):
    with db.session() as conn:
        job = _job_or_404(conn, job_id)
    profile.append_facts(body.facts, f"{job['role']} @ {job['company']}")
    return {"ok": True}


@app.post("/api/voice/note")
def voice_note(body: TextIn):
    """'Remember this' in the message composer: a tone correction every future draft follows."""
    profile.add_tone_note(body.text)
    return {"ok": True}


@app.post("/api/work-auth")
def work_auth(page: PageIn):
    """Side panel on a job page I haven't saved yet: does my work authorization allow applying?"""
    return _work_auth(page.text, profile.me()) or {"verdict": "unknown", "reason": "Set visa_status in Me to enable.", "quote": ""}


class PicksIn(BaseModel):
    variant: str = "A"
    base_version: str = ""                       # e.g. "Version H: AI Product / PM"
    picks: list[dict] = []                       # [{experience, include, how}]
    note: str = ""


@app.post("/api/jobs/{job_id}/rebuild-with-picks")
def rebuild_with_picks(job_id: int, body: PicksIn):
    """The experience picker: I dictate what goes in and how; the coach rebuilds exactly that (still one page)."""
    keep = [p for p in body.picks if p.get("include")]
    drop = [p["experience"] for p in body.picks if not p.get("include")]
    lines = ["Rebuild my resume following MY PICKS EXACTLY (these override your own ranking):"]
    if body.base_version:
        lines.append(f"- Base the wording on my resume '{body.base_version}' wherever it covers an item.")
    if keep:
        lines.append("- INCLUDE, in this order within each section:")
        lines += [f"  - {p['experience']}" + (f" -> {p['how']}" if (p.get('how') or '').strip() else "") for p in keep]
    if drop:
        lines.append("- REMOVE completely: " + "; ".join(drop))
    if body.note.strip():
        lines.append(f"- Also: {body.note.strip()}")
    lines.append("- Keep it ONE page: if my picks don't fit, shorten bullets (fewer per item) rather than dropping an item I picked.")
    return post_resume_chat(job_id, ChatIn(message="\n".join(lines), variant=body.variant))


@app.post("/api/roles/pull-latest")
def import_latest(limit: int = 100):
    """Newest US entry-level PM / adjacent roles (SimplifyJobs public lists) into my 'New roles' inbox (priority 3)."""
    me = profile.me()
    rows = sources.with_descriptions(sources.candidates(me, limit))
    added = skipped = blocked = 0
    with db.session() as conn:
        for r in rows:
            key = url_key(r["url"])
            if key and one(conn.execute("SELECT id FROM jobs WHERE url_key = ?", (key,))):
                skipped += 1
                continue
            note = (f"Source: SimplifyJobs ({r['kind']}{', ' + r['terms'] if r['terms'] else ''}) · posted "
                    f"{sources.posted_date(r['posted'])} · sponsorship: {r['sponsorship']}")
            conn.execute("""INSERT INTO jobs (company, role, url, url_key, location, jd, priority, notes)
                            VALUES (?, ?, ?, ?, ?, ?, 3, ?)""",
                         (r["company"], r["role"], r["url"], key, r["location"], r.get("jd", ""), note))
            added += 1
            if r.get("jd") and workauth.check(r["jd"])["verdict"] == "dont_apply":
                blocked += 1
    with_jd = sum(1 for r in rows if r.get("jd"))
    return {"added": added, "already_had": skipped, "with_description": with_jd, "not_for_f1": blocked}


@app.get("/api/general-resume.pdf")
def general_resume(download: bool = True):
    """My send-anywhere resume (PM / APM / project / product builder / AI analyst / AI consultant)."""
    with db.session() as conn:
        job = one(conn.execute("SELECT * FROM jobs WHERE company = 'General' ORDER BY id DESC"))
    if not job:
        raise HTTPException(404, "No general resume yet")
    return job_resume_pdf(job["id"], download=download, variant="A")
