"""Resume -> LaTeX -> PDF, named and ready to upload (e.g. into Simplify's resume slot).

Two modes:
- Template mode (default): Claude returns structured content, we render it into TEMPLATE below.
  Escaping is done here, so the PDF always compiles.
- Your-own-.tex mode: if profile/resume.tex exists, Claude edits a fresh copy of it with surgical
  changes (the ai-job-application-kit resume-tailor workflow) and we compile that.

Compiler: pdflatex, else xelatex, else tectonic (`brew install tectonic`).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .db import ROOT

RESUMES = ROOT / "data" / "resumes"

TEMPLATE = r"""\documentclass[letterpaper,11pt]{article}
% Only core packages, so it compiles on a minimal TinyTeX / BasicTeX install.
\usepackage[margin=0.5in]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\ifdefined\pdfgentounicode \input{glyphtounicode}\pdfgentounicode=1 \fi % ATS-readable text
\pagestyle{empty}
\setlength{\parindent}{0pt}
\newcommand{\rsection}[1]{\vspace{7pt}{\large\bfseries\scshape #1}\par\vspace{-4pt}\rule{\linewidth}{0.4pt}\par\vspace{2pt}}
\newenvironment{bullets}{\begin{list}{\textbullet}{\setlength{\leftmargin}{1.2em}\setlength{\itemsep}{0.5pt}%
  \setlength{\topsep}{1pt}\setlength{\parsep}{0pt}\setlength{\partopsep}{0pt}}}{\end{list}}
\newcommand{\entry}[4]{\textbf{#1}\hfill #3\\ #2\hfill #4\par}
\begin{document}
\begin{center}
  {\LARGE\bfseries <<NAME>>}\\[3pt]
  \small <<CONTACTS>>
\end{center}
<<BODY>>
\end{document}
"""

_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def esc(s: str) -> str:
    s = "".join(_ESC.get(c, c) for c in (s or ""))
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)  # **bold** from the model
    return s.replace("—", ", ").replace("–", "--")


def _contact(c: str) -> str:
    c = c.strip()
    if "@" in c and " " not in c:
        return rf"\href{{mailto:{c}}}{{{esc(c)}}}"
    if re.match(r"^(https?://)?([\w-]+\.)+\w+(/\S*)?$", c) and "." in c:
        url = c if c.startswith("http") else f"https://{c}"
        return rf"\href{{{url}}}{{{esc(re.sub(r'^https?://(www\.)?', '', c))}}}"
    return esc(c)


def render(resume: dict) -> str:
    body = []
    for sec in resume["sections"]:
        body.append(rf"\rsection{{{esc(sec['title'])}}}")
        for line in sec.get("lines") or []:
            body.append(esc(line) + r"\par")
        for e in sec.get("entries") or []:
            body.append(rf"\entry{{{esc(e['heading'])}}}{{{esc(e['subheading'])}}}{{{esc(e['date'])}}}{{{esc(e['location'])}}}")
            if e.get("bullets"):
                body.append(r"\begin{bullets}")
                body += [rf"  \item {esc(b)}" for b in e["bullets"]]
                body.append(r"\end{bullets}")
            body.append(r"\vspace{2pt}")
    return (TEMPLATE.replace("<<NAME>>", esc(resume["name"]))
            .replace("<<CONTACTS>>", r" $\cdot$ ".join(_contact(c) for c in resume["contacts"] if c.strip()))
            .replace("<<BODY>>", "\n".join(body)))


def compiler() -> list[str] | None:
    for cmd in (["pdflatex", "-interaction=nonstopmode", "-halt-on-error"],
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error"],
                ["tectonic"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def _pages(log: str) -> int:
    """pdflatex/xelatex print 'Output written on X.pdf (1 page, ...)'."""
    m = re.search(r"\((\d+) pages?", log)
    return int(m.group(1)) if m else 1


def filename(me: dict, company: str) -> str:
    """Jane_Doe_Resume_Stripe.pdf: your name first so the recruiter knows whose it is."""
    name = "_".join(re.findall(r"[A-Za-z0-9]+", me.get("name") or "")) or "Resume"
    if company.strip().lower() in ("", "general", "any company"):
        return f"{name}_Resume.pdf" if name != "Resume" else "Resume.pdf"   # the general, send-anywhere resume
    comp = "".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", company))[:30]
    return f"{name}_Resume_{comp}.pdf" if name != "Resume" else f"Resume_{comp}.pdf"


def job_dir(job: dict, variant: str = "A") -> Path:
    """Same file name for both versions (recruiters see Jane_Doe_Resume_X.pdf), different folders."""
    slug = lambda s: re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40]
    base = RESUMES / f"{slug(job['company'])}_{slug(job['role'])}_{job['id']}"
    return base if variant == "A" else base / f"version-{variant}"


def compile_tex(tex: str, job: dict, me: dict, variant: str = "A") -> dict:
    """Writes .tex, compiles, returns {pdf, pages, error}. The .tex is kept even if compile fails."""
    d = job_dir(job, variant)
    d.mkdir(parents=True, exist_ok=True)
    stem = filename(me, job["company"])[:-4]
    (d / f"{stem}.tex").write_text(tex)
    cmd = compiler()
    if not cmd:
        return {"pdf": None, "pages": 0, "error": "No LaTeX compiler found. Install one: brew install tectonic"}
    try:
        run = subprocess.run([*cmd, f"{stem}.tex"], cwd=d, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"pdf": None, "pages": 0, "error": "LaTeX compile timed out"}
    pdf = d / f"{stem}.pdf"
    for ext in (".aux", ".log", ".out"):
        if run.returncode == 0:
            (d / f"{stem}{ext}").unlink(missing_ok=True)
    if run.returncode != 0 or not pdf.exists():
        errors = [l for l in run.stdout.splitlines() if l.startswith("!")][:3]
        return {"pdf": None, "pages": 0, "error": "LaTeX error: " + (" ".join(errors) or run.stdout[-400:])}
    return {"pdf": str(pdf), "pages": _pages(run.stdout + run.stderr), "error": None}


def pdf_for(job: dict, me: dict, variant: str = "A") -> Path | None:
    p = job_dir(job, variant) / filename(me, job["company"])
    return p if p.exists() else None


def plain_text(tex: str) -> str:
    """Rough visible text of a .tex resume, for keyword matching."""
    body = tex.split("\\begin{document}", 1)[-1]
    body = re.sub(r"%.*", "", body)
    body = re.sub(r"\\href\{[^}]*\}", "", body)          # drop link targets, keep link text
    body = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", body)  # commands
    body = body.replace("\\&", "&").replace("\\%", "%").replace("\\$", "$").replace("\\#", "#").replace("\\_", "_")
    return re.sub(r"[{}]", " ", body)


def short_lines(pdf: str | Path, ratio: float = 0.62) -> list[dict]:
    """Lines that END SHORT (white space on the right): a bullet's last line with a few words, a skills/coursework
    line that spills one word, etc. Measured from the real PDF, so bold/wide text is accounted for."""
    import pypdf
    from collections import defaultdict
    page = pypdf.PdfReader(str(pdf)).pages[0]
    parts = []

    def visit(text, cm, tm, fd, fs):
        if text.strip():
            y = tm[5] * cm[3] + cm[5]
            parts.append((round(y), tm[4] * cm[0] + cm[4], text, fs * (tm[0] or 1)))
    page.extract_text(visitor_text=visit)
    rows = defaultdict(list)
    for y, x, t, fs in parts:
        rows[y].append((x, t, fs))
    ordered = []
    for y in sorted(rows, reverse=True):
        xs = sorted(rows[y])
        text = "".join(t for _, t, _ in xs).replace("\n", " ").strip()
        ordered.append({"y": y, "x0": xs[0][0], "text": text, "chars": len(text), "font": max(f for _, _, f in xs)})
    if not ordered:
        return []
    full = sorted(r["chars"] for r in ordered)[int(len(ordered) * 0.9)]  # a typical full line
    margin = min(r["x0"] for r in ordered)
    out = []
    in_skills = False
    for prev, row in zip(ordered, ordered[1:]):
        text = row["text"]
        if text in ("Skills", "Technical Skills", "Skills & Tools"):
            in_skills = True
            continue
        dated = re.search(r"(19|20)\d\d", text)
        education = re.search(r"Certificates|Coursework|Expected|Graduation|GPA", text)
        if dated or education:
            continue
        fill = round(row["chars"] / full, 2)
        continuation = row["x0"] > margin + 5 or (prev["chars"] >= 0.8 * full and abs(row["font"] - prev["font"]) < 0.5)
        wrapped_skill = in_skills and not re.search(r"[A-Za-z]+:", text)   # a skills line that spilled (no "Label:")
        if continuation and (not in_skills or wrapped_skill) and prev["chars"] >= 0.8 * full and row["chars"] < ratio * full:
            out.append({"line": text, "previous": prev["text"], "fill": fill})        # bullet/line ending short
        # skills lines are allowed to end early (curated, not cluttered); only their wraps are caught above
    return out


def free_lines(pdf: str | Path) -> float:
    """How many text lines of empty space are left at the bottom of page 1."""
    import pypdf
    page = pypdf.PdfReader(str(pdf)).pages[0]
    ys = []

    def visit(text, cm, tm, fd, fs):
        if text.strip():
            ys.append(tm[5] * cm[3] + cm[5])
    page.extract_text(visitor_text=visit)
    if not ys:
        return 0.0
    height = float(page.mediabox.height)
    margin = min(max(height - max(ys) - 17, 18), 72)  # top margin ~= bottom margin in my layouts
    return round(max(min(ys) - margin, 0) / 11.5, 1)   # ~11.5pt per resume line


GAP_MACRO = "\\newlength{\\jobosgap}\\setlength{\\jobosgap}{%.2fpt}"
ITEM_GAP_CAP = 2.0  # pt; past this, bullets look stretched: add content instead
ENTRY_GAP_CAP = 2.0  # pt; New grad version uses ~0.8pt, so roles never look far apart


def _with_gap(tex: str, gap_pt: float) -> str:
    """Insert an adjustable gap before every section and every entry in the body."""
    pre, sep, body = tex.partition("\\begin{document}")
    if not sep:
        return tex
    pre = re.sub(r"\\newlength\{\\jobosgap\}\\setlength\{\\jobosgap\}\{[^}]*\}\n?", "", pre)
    body = body.replace("\\vspace{\\jobosgap}", "")
    body = re.sub(r"(?m)^(\s*)(\\resumeSubheading(Orig)?\b|\\resumeEduHeading\b|\\resumeProjectHeading\b|\\entry\{)",
                  lambda m: m.group(1) + "\\vspace{\\jobosgap}" + m.group(2), body)
    # ...but never on the FIRST entry of a section: the space under a section's line stays fixed
    body = re.sub(r"(\\resumeSubHeadingListStart\s*(?:%[^\n]*\n\s*)*)\\vspace\{\\jobosgap\}", r"\1", body)
    # entries get the page-fill space only up to ENTRY_GAP_CAP (bigger looks like holes between roles);
    # anything beyond that goes between bullets instead, so the page still ends at the bottom
    entry = min(gap_pt, ENTRY_GAP_CAP)
    extra = ""
    if "\\jobositemsep" in pre:
        extra += "\\setlength{\\jobositemsep}{%.2fpt}" % min(max((gap_pt - ENTRY_GAP_CAP) * 0.4, 0), ITEM_GAP_CAP)
    if "\\joboseduskip" in pre:
        extra += "\\setlength{\\joboseduskip}{0pt}"
    # drop settings left by earlier passes, keeping the template's own \newlength definitions
    pre = re.sub(r"(\\newlength\{\\jobos(?:itemsep|eduskip)\})?\\setlength\{\\jobos(itemsep|eduskip)\}\{[^}]*\}",
                 lambda m: m.group(0) if m.group(1) else "", pre)
    return pre + (GAP_MACRO % entry) + extra + "\n" + sep + body


def stretch_to_fill(tex: str, job: dict, me: dict, variant: str = "A") -> tuple[str, dict]:
    """Make the page end right at the bottom by adjusting the gap before each entry:
    - leftover space -> spread it out; - slight overflow to page 2 -> tighten (down to -3pt per entry).
    Pure measurement: never changes wording, and never returns a 2-page result if a 1-page one exists."""
    body = tex.partition("\\begin{document}")[2]
    gaps = len(re.findall(r"(?m)^\s*(\\vspace\{\\jobosgap\})?(\\resumeSubheading|\\resumeEduHeading|\\resumeProjectHeading|\\entry\{)", body))
    built = compile_tex(tex, job, me, variant)
    if built["error"] or gaps == 0:
        return tex, built
    if built["pages"] > 1:                                  # overflow: tighten (relative to the current gap) until it fits
        now = float(re.search(r"jobosgap\}\{(-?[\d.]+)pt", tex).group(1)) if "jobosgap}{" in tex else 0.0
        for gap in (now - 0.75, now - 1.5, now - 2.25, now - 3.0):
            trial = _with_gap(tex, gap)
            b = compile_tex(trial, job, me, variant)
            if not b["error"] and b["pages"] == 1:
                tex, built = trial, b
                break
        else:
            compile_tex(tex, job, me, variant)
            return tex, built
    free_pt = free_lines(built["pdf"]) * 11.5
    if free_pt < 6:
        return tex, built
    current = float(re.search(r"jobosgap\}\{(-?[\d.]+)pt", tex).group(1)) if "jobosgap}{" in tex else 0.0
    best_tex, best = tex, built
    gap = current + free_pt * 0.85 / gaps
    for _ in range(5):
        trial = _with_gap(tex, gap)
        b = compile_tex(trial, job, me, variant)
        if b["error"] or b["pages"] != 1:
            gap = current + (gap - current) * 0.6       # overflowed: back off
            continue
        best_tex, best = trial, b
        left = free_lines(b["pdf"]) * 11.5
        if left < 8:
            break
        gap += left * 0.8 / gaps
    compile_tex(best_tex, job, me, variant)                 # the saved PDF is the best one
    return best_tex, best


STACK_TERMS = [
    "RAG", "LLMs?", "Python", "SQL", "Snowflake", "Tableau", "PostHog", "Mixpanel", "A/B testing", "React/MongoDB",
    "React", "MongoDB", "Miro", "Typeform", "Figma", "v0", "RICE", "K-Means", "PCA", "Azure OpenAI", "Tesseract",
    "TypeScript", "Cloudflare Workers AI", "Excel", "JMP", "Mode", "Streamlit", "scikit-learn", "pandas", "XGBoost", "CatBoost", "NumPy",
    "Google, Yelp, and BBB APIs", "multi-API pipeline", "agile sprints", "PRD", "Jira",
]


def bold_stack(tex: str, terms: list[str] = STACK_TERMS) -> str:
    """Bold tools / stack names inside resume bullets (not in Skills), skipping anything already bold."""
    def fix(m):
        inner = m.group(1)
        for t in sorted(terms, key=len, reverse=True):
            inner = re.sub(r"(?<![\\{A-Za-z])(" + t + r")(?![A-Za-z}])",
                           lambda x: x.group(1) if _inside_bold(inner, x.start()) else "\\textbf{" + x.group(1) + "}", inner)
        return "\\resumeItem{" + inner + "}"
    return re.sub(r"\\resumeItem\{(.*)\}", fix, tex)


def _inside_bold(text: str, pos: int) -> bool:
    open_at = text.rfind("\\textbf{", 0, pos)
    return open_at != -1 and text.find("}", open_at) > pos


def normalize_spacing(tex: str, after_section: str = "2.9pt", section_gap: str = "-7pt") -> str:  # measured: makes every gap above a section heading equal
    """One spacing system instead of piled-up one-off tweaks: the same gap after every section heading, and no
    ad-hoc \\vspace lines between entries (entry gaps then come only from the macros + the page-fill gap)."""
    pre, sep, body = tex.partition("\\begin{document}")
    if not sep:
        return tex
    head_end = body.find("\\end{center}")
    head, rest = (body[:head_end], body[head_end:]) if head_end != -1 else ("", body)
    lines, out = rest.split("\n"), []
    for i, line in enumerate(lines):
        if re.fullmatch(r"\s*\\vspace\{-?[\d.]+pt\}\s*", line):
            prev = next((l for l in reversed(out) if l.strip()), "")
            if prev.strip().startswith("\\section{"):
                out.append("\\vspace{%s}" % after_section)   # same gap after every section heading
            continue                                            # drop ad-hoc gaps between entries/sections
        out.append(line)
        if line.strip().startswith("\\section{"):
            nxt = next((l for l in lines[i + 1:] if l.strip()), "")
            if not re.fullmatch(r"\s*\\vspace\{-?[\d.]+pt\}\s*", nxt):
                out.append("\\vspace{%s}" % after_section)
    rest = "\n".join(out)
    # Same gap above EVERY section heading. Sections that end with a bullet list sit ~4pt higher than Education
    # (which ends with plain lines), so they get +4pt; Education gets none.
    parts = re.split(r"(?m)^(?=\\section\{)", rest)
    fixed = [parts[0]]
    for prev, cur in zip(parts, parts[1:]):
        clean = re.sub(r"(\n[ \t]*%[^\n]*)+\s*$", "", prev.rstrip()).rstrip()   # ignore "%----SECTION----" comments
        prev_ends_with_bullets = clean.endswith("\\resumeSubHeadingListEnd") and "\\resumeItemListEnd" in clean[-400:]
        if prev_ends_with_bullets and not fixed[-1].rstrip().endswith("\\vspace{%s}" % section_gap):
            fixed[-1] = fixed[-1].rstrip("\n") + "\n\\vspace{%s}\n" % section_gap
        fixed.append(cur)
    return pre + sep + head + "".join(fixed)


def unbold_bullets(tex: str) -> str:
    """No bold inside bullets (my rule): strip \\textbf{...} within \\resumeItem{...} only. Headings, dates and
    skill labels keep their bold."""
    def fix(m):
        inner = m.group(1)
        while True:
            new = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", inner)
            if new == inner:
                return "\\resumeItem{" + inner + "}"
            inner = new
    return re.sub(r"\\resumeItem\{(.*)\}", fix, tex)


_NUM = re.compile(r"(?<![\w{\\.])(\$?\d[\d,]*(?:\.\d+)?(?:\\%|K\+|K|M\+|M|\+)?)(?![\w}])")


def bold_numbers(tex: str) -> str:
    """Bold metrics inside bullets (45%, 20+, 12K+, 3,500, 92.5%, 10K ...), skipping anything already bold."""
    def fix(m):
        inner = m.group(1)
        out, last = [], 0
        for n in _NUM.finditer(inner):
            if _inside_bold(inner, n.start()):
                continue
            out.append(inner[last:n.start()] + "\\textbf{" + n.group(1) + "}")
            last = n.end()
        return "\\resumeItem{" + "".join(out) + inner[last:] + "}"
    return re.sub(r"\\resumeItem\{(.*)\}", fix, tex)


def unbold_gpa(tex: str) -> str:
    return re.sub(r"(GPA:?\s*)\\textbf\{([\d.]+)\}", r"\1\2", tex)


def keep_together(tex: str) -> str:
    """No line break between a number and its noun ('20+ tasks') or inside multi-word tech names ('Azure OpenAI')."""
    def fix(m):
        inner = m.group(1)
        inner = re.sub(r"(\\textbf\{[^{}]*\d[^{}]*\}) (?=[A-Za-z])", r"\1~", inner)
        for name in ("Azure OpenAI", "Cloudflare Workers AI", "Six Sigma", "K-Means clustering", "React/MongoDB"):
            inner = inner.replace(name, name.replace(" ", "~"))
        return "\\resumeItem{" + inner + "}"
    return re.sub(r"\\resumeItem\{(.*)\}", fix, tex)


def section_gaps(pdf) -> dict:
    """Measured distance (pt) from the line above each section heading to the heading."""
    import pypdf
    page = pypdf.PdfReader(str(pdf)).pages[0]
    rows = {}

    def visit(text, cm, tm, fd, fs):
        if text.strip():
            rows.setdefault(round(tm[5] * cm[3] + cm[5], 1), []).append(text.strip())
    page.extract_text(visitor_text=visit)
    ys = sorted(rows, reverse=True)
    heads = re.findall(r"\\section\{([^}]*)\}", "")  # filled by caller via names
    out = {}
    for i, y in enumerate(ys):
        t = " ".join(rows[y])
        if i and t in SECTION_NAMES:
            out[t] = round(ys[i - 1] - y, 1)
    return out


SECTION_NAMES = {"Education", "Professional Experience", "Experience", "Project", "Projects", "Leadership", "Skills"}


def equalize_section_gaps(tex: str, job: dict, me: dict, variant: str = "A") -> tuple[str, dict]:
    """Make the gap above every section heading the same, measured in the real PDF. Only touches the gap lines
    that normalize_spacing puts before headings that follow bullet lists. Never allows a second page."""
    built = compile_tex(tex, job, me, variant)
    for _ in range(4):
        if built["error"] or built["pages"] != 1:
            break
        g = section_gaps(built["pdf"])
        target = g.get("Professional Experience") or g.get("Experience")
        after_lists = [v for k, v in g.items() if k not in ("Education", "Professional Experience", "Experience")]
        if not target or not after_lists:
            break
        delta = target - sum(after_lists) / len(after_lists)
        if abs(delta) < 0.5:
            break
        m = re.search(r"(?m)^\\vspace\{(-?[\d.]+)pt\}(?=\n(?:%[^\n]*\n)*\\section\{)", tex)
        if not m:
            break
        cur = float(m.group(1))
        new = round(cur + delta, 2)
        trial = re.sub(r"(?m)^\\vspace\{-?[\d.]+pt\}(?=\n(?:%[^\n]*\n)*\\section\{)",
                       lambda _m: "\\vspace{%.2fpt}" % new, tex)   # lambda: avoid "\v" escape in re.sub
        b = compile_tex(trial, job, me, variant)
        if not b["error"] and b["pages"] != 1:
            trial, b = stretch_to_fill(trial, job, me, variant)   # take the space back from the entry gaps
        if b["error"] or b["pages"] != 1:
            break
        tex, built = trial, b
    compile_tex(tex, job, me, variant)
    return tex, built


def fact_guard(tex: str) -> str:
    """Corrections I've confirmed, enforced in code so old wording from older resume versions can't sneak back."""
    # RAG spelled out in every bullet that mentions it
    def item(m):
        t = m.group(0)
        if "RAG" in t and "Retrieval-Augmented" not in t:
            t = re.sub(r"(\\textbf\{)?RAG(\})?-powered\s+", "Retrieval-Augmented Generation (\\\\textbf{RAG}) ", t, count=1)
            if "Retrieval-Augmented" not in t:
                t = re.sub(r"(\\textbf\{RAG\}|\bRAG\b)", lambda mm: "Retrieval-Augmented Generation (" + mm.group(0) + ")", t, count=1)
        return t
    tex = re.sub(r"\\resumeItem\{[^\n]*", item, tex)
    # my own confirmed corrections live in profile/fact-fixes.json (private): [[regex, replacement], ...]
    fixes = Path(__file__).resolve().parent.parent / "profile" / "fact-fixes.json"
    if fixes.exists():
        for pattern, repl in json.loads(fixes.read_text()).get("replace", []):
            tex = re.sub(pattern, repl, tex)
    # graduation line always reads "Expected Graduation: MM/YYYY"
    tex = re.sub(r"\{Expected (\d\d/)", r"{Expected Graduation: \1", tex)
    return tex
