"""All model calls. Claude by default; with JOBOS_WRITER=openai, the LANGUAGE work (resume wording, resume chat,
outreach messages) goes to OpenAI and the TECHNICAL work (LaTeX, one-page fitting, reading pages, fit checks)
stays on Claude. Prompts are assembled from the copied repos (MIT, see third_party/):

- GUARDRAILS: ai-job-application-kit AGENTS.md ("Guardrails - do not fabricate", no em dashes).
- tailor_resume: ai-job-application-kit resume-tailor skill (surgical edits, <=2 bullet swaps per
  role, never invent) + job-search-skills job-analyzer "do not overload the resume" philosophy.
- fit_check: job-analyzer Step 5 compatibility assessment (STRONG / PARTIAL / GAP).
- draft_message: Recruiting OS lib/drafting.js (personalization-first cold open, follow-up
  escalation tiers) + job-analyzer's intro-email structure, written in MY voice (profile/voice.md).
"""
import json
import os
import re

import anthropic

from . import profile

MODEL = os.environ.get("JOBOS_MODEL", "claude-opus-5-5")
WRITER = os.environ.get("JOBOS_WRITER", "claude").lower()          # claude | openai
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

GUARDRAILS = """Guardrails, do not fabricate. Never invent employment dates, company names, tools, metrics,
impact numbers, or outcomes. Only claim what is backed by the candidate's resume / experience files.
When unsure of the candidate's exact role in something, use safer verbs ("worked on", "contributed to").
Never use em dashes. Use commas, "and", or rewrite the sentence. Em dashes read as AI-generated."""

_client = None


class AIError(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


MATERIALS_NOTE = """How to read my materials: my master resume is deliberately MESSY. It holds several resume versions
written for different kinds of roles, plus narratives of what I actually did in each role. The same experience
is often described in different ways across versions. Treat ALL of it together as the full picture of what I did.
Any fact (task, tool, stakeholder, result, number) that appears in ANY version or narrative is true and usable,
EXCEPT where a newer source corrects it. When sources disagree, this order wins (newest rules first):
  1. RESUME PREFERENCES (style and layout rules),
  2. the "Confirmed" sections and "NEW FACT" / "Preferred bullets" lines in NARRATIVES (my latest corrections:
     e.g. a corrected number; shared work described as "co-developed"; no unexplained projections),
  3. the ROLE-FAMILY PLAYBOOK's BASE bullets (my current approved wording),
  4. the rest of NARRATIVES,
  5. the MASTER RESUME versions (oldest; never copy an outdated number or the word "Link" from them).
Where versions still disagree on a number, use the more conservative one."""


def _targets_block() -> str:
    me = profile.me()
    roles = ", ".join(me.get("target_roles") or []) or "(not set)"
    avoid = ", ".join(me.get("avoid_roles") or []) or "(none)"
    rules = []
    if me.get("grad_date_internship") or me.get("grad_date_full_time"):
        rules.append(f"Expected graduation date on the resume: internship/co-op roles -> {me.get('grad_date_internship') or 'as in my resume'}; "
                     f"new-grad/full-time roles -> {me.get('grad_date_full_time') or 'as in my resume'}. Decide from the JD which one this is. "
                     f"If the JD requires a graduation date later than the chosen one (e.g. 'November 2027 or later'), use the internship date. "
                     f"Always write it as 'Expected Graduation: MM/YYYY'.")
    if me.get("gpa"):
        rules.append(f"GPA: my GPA is {me['gpa']}. Include it ONLY if the JD mentions a GPA requirement or asks for GPA; then write "
                     f"exactly {me['gpa']} (never round up). Otherwise leave GPA off. If the JD's minimum is above {me['gpa']}, "
                     f"say so in gaps / the fit verdict.")
    if me.get("visa_status"):
        rules.append(f"Work authorization: I'm an {me['visa_status']}. If the JD requires US citizenship / permanent residency / "
                     "permanent or indefinite work authorization, excludes OPT/CPT/F-1, or needs a clearance, say 'Not eligible "
                     "on F-1' first in the verdict and score it 0. A plain 'no sponsorship / no H-1B' is fine: still apply.")
    st = me.get("skill_stretch") or {}
    if st.get("enabled"):
        rules.append(
            f"Skills stretch (SKILLS SECTION ONLY): if my resume would cover less than {st.get('below_match_pct', 80)}% of the "
            "JD's must-have keywords, you MAY add JD tools/skills I haven't used to the Skills section when they are "
            "(a) adjacent to something I have used (Tableau -> Power BI / Looker, Mixpanel/PostHog -> Amplitude / GA4, "
            "Jira -> Asana / Linear, Snowflake -> BigQuery / Redshift, Figma -> Sketch) or (b) a tool/platform I can get "
            f"hands-on with in about {st.get('learn_within_days', 7)} days (AI tools, SaaS analytics, AWS/GCP basics). "
            "NEVER put them in experience bullets, never claim years of experience or deep expertise. "
            "List EVERY such added skill in `stretch_skills` so I learn it before interviews. "
            "Certifications: only if a well-known certification would materially help me get THIS interview (the JD asks "
            "for it or screens on that area) and is doable in about 1-2 weeks (e.g. AWS Cloud Practitioner, Google Data "
            "Analytics, PSM I / PSPO I, Google Project Management), you may add at most 2 as '<Name> (in progress)' in the "
            "certificates line. List each in `certs_to_start`: I will START it before submitting so 'in progress' is true. "
            "Never list a certification as completed unless my materials say so.")
    rule_text = ("\nApplication rules:\n- " + "\n- ".join(rules)) if rules else ""
    return (f"<MY TARGETS>\nI apply broadly across role families where my skills transfer: {roles}.\n"
            f"Roles I do NOT want / don't fit: {avoid}.{rule_text}\n</MY TARGETS>")


def _me_block() -> str:
    parts = [MATERIALS_NOTE, _targets_block()]
    if profile.playbooks_block():
        parts.append(profile.playbooks_block())
    for name, label in [("resume", "MASTER RESUME (multiple versions, messy on purpose)"),
                        ("experience", "NARRATIVES (the full story behind each role)"),
                        ("profile", "PROFILE / TARGETS"), ("resume-preferences", "RESUME PREFERENCES")]:
        text = profile.real_or_blank(name)
        if text.strip():
            parts.append(f"<{label}>\n{text.strip()}\n</{label}>")
    if not profile.real_or_blank("resume").strip():
        raise AIError("Fill in your master resume first (Me tab > resume).")
    return "\n\n".join(parts)


def job_angle(job: dict) -> str:
    try:
        return json.loads(job.get("fit_notes") or "{}").get("angle", "")
    except ValueError:
        return ""


def company_certs(job: dict) -> list[str]:
    from .warmpaths import same_company
    for company, certs in (profile.me().get("company_certs") or {}).items():
        if same_company(job.get("company", ""), company):
            return certs
    return []


def _job_block(job: dict) -> str:
    angle = job_angle(job)
    certs = company_certs(job)
    if certs:
        angle_hint_certs = ("\nREQUIRED for this company: list " + "; ".join(f"'{c} (in progress)'" for c in certs) +
                            " in the certificates line, and include each in `certs_to_start`.")
    else:
        angle_hint_certs = ""
    hint = f"\nAngle suggested by my fit check (use it unless the JD clearly calls for another): {angle}" if angle else ""
    return (f"<JOB>\nCompany: {job['company']}\nRole: {job['role']}\nLocation: {job.get('location') or '?'}\n"
            f"URL: {job.get('url') or '?'}\n\nJob description:\n{job.get('jd') or '(not pasted)'}{hint}{angle_hint_certs}\n</JOB>")


def _no_em_dash(s: str) -> str:
    # em dash only; en dashes stay because resumes use them in date ranges
    return re.sub(r"\s*—\s*", ", ", s) if isinstance(s, str) else s


def _call(prompt, schema: dict, effort: str = "medium", max_tokens: int = 16000, task: str = "technical") -> dict:
    """task='writing' -> OpenAI when JOBOS_WRITER=openai; everything else -> Claude."""
    if task == "writing" and WRITER == "openai":
        return _call_openai(prompt, schema, effort, max_tokens)
    try:
        # Streamed so long outputs (a full tailored .tex) don't hit HTTP timeouts.
        with client().beta.messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            system=GUARDRAILS,
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            # If a safety classifier declines, the API retries on a fallback model automatically.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            resp = stream.get_final_message()
    except (anthropic.AuthenticationError, TypeError) as e:
        if isinstance(e, TypeError) and "authentication" not in str(e):  # a real bug, don't mask it
            raise
        raise AIError("No Anthropic API key. Put ANTHROPIC_API_KEY=... in .env (see .env.example) and restart ./run.sh.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Rate limited by the API, try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Couldn't reach the Claude API. Check your internet connection.") from e

    if resp.stop_reason == "refusal":
        raise AIError("Claude declined this request.")
    if resp.stop_reason == "max_tokens":
        raise AIError("Response was cut off. Try again, or shorten the job description.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


_openai_client = None


def _call_openai(prompt: str, schema: dict, effort: str, max_tokens: int) -> dict:
    import openai
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.OpenAI()
    try:
        resp = _openai_client.responses.create(
            model=OPENAI_MODEL,
            instructions=GUARDRAILS,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}},
            reasoning={"effort": {"low": "low", "medium": "medium"}.get(effort, "high")},
            max_output_tokens=max(max_tokens, 16000),
        )
    except openai.AuthenticationError as e:
        raise AIError("No valid OpenAI API key. Put OPENAI_API_KEY=... in .env and restart ./run.sh.") from e
    except openai.RateLimitError as e:
        raise AIError("OpenAI rate limit or quota hit, try again in a minute (or check billing).") from e
    except openai.APIStatusError as e:
        raise AIError(f"OpenAI API error {e.status_code}: {e.message}") from e
    except openai.APIConnectionError as e:
        raise AIError("Couldn't reach the OpenAI API. Check your internet connection.") from e
    except openai.OpenAIError as e:  # e.g. no key configured at all
        raise AIError(f"OpenAI not configured: {e}") from e
    if resp.status == "incomplete":
        raise AIError("OpenAI response was cut off. Try again, or shorten the job description.")
    if not resp.output_text:
        raise AIError("OpenAI returned nothing (possibly declined).")
    return json.loads(resp.output_text)


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


STR = {"type": "string"}
STRS = {"type": "array", "items": STR}


# ---------------------------------------------------------------------------------------
def extract_job(pasted: str) -> dict:
    """Paste a whole job posting, get the fields back. Less typing = more applying."""
    return _call(
        "Extract the job fields from this job posting page. Use '' for anything not present. "
        "If the page shows a list of jobs plus one job's details (e.g. LinkedIn search), extract the one whose details are shown. "
        "Keep `jd` as the full cleaned-up description text (responsibilities + requirements), not a summary.\n\n"
        f"<POSTING>\n{pasted}\n</POSTING>",
        _obj({"company": STR, "role": STR, "location": STR, "url": STR, "jd": STR}),
        effort="low",
    )


def fit_check(job: dict) -> dict:
    result = _call(
        f"""{_me_block()}

{_job_block(job)}

Give an honest, at-a-glance fit assessment (job-analyzer style).
- First decide which role family this JD really is (e.g. data analyst, product analyst, PM, product ops,
  marketing analytics, data science, AI automation, digital transformation, tech/AI consulting), whatever
  the title says. Judge me on TRANSFERABLE skills for that family, not on whether my past titles match.
  A data/AI background often fits marketing analytics, product, ops and consulting roles; say so when true.
- If it's one of the roles I said I don't want, say that in the verdict and score it low.
- For each major JD requirement: level STRONG (direct, clear match), PARTIAL (adjacent experience), or GAP.
- unique_strengths: what I bring that most candidates won't.
- gaps: be straightforward, note learnability.
- emphasize: the 3 things from my background to lead with for THIS role.
- experience_ranking: EVERY role, leadership item and project in my materials (one row each, no duplicates across
  versions), scored 0-100 for THIS JD: how much of what the JD needs it proves, SAME-INDUSTRY/DOMAIN RELEVANCE
  (weight heavily, use my Domain map), how strong its results are, how recent.
  include=true for the ones that should make a ONE-PAGE resume (about 4 experiences + 2-3 projects), and `how` = one
  short line on how to frame it for this JD (which bullet/angle to lead with). Sort best first.
- jd_keywords: the 12-20 must-have keywords/skills/tools an ATS would scan for in this JD, exactly as the JD spells them.
- domain: the company's industry, and my strongest proof of knowing it (from my Domain map), in one line.
- angle: one sentence, the story/positioning to use for this role family (e.g. "analyst who turns messy data
  into decisions for marketing teams"). The resume tailor and outreach messages reuse it.
- verdict: 1-2 honest sentences. "Strong fit for X, but Y is a gap" beats a vague score.
- score: 0-100, how likely I am to get an interview if a human reads my tailored resume.""",
        _obj({
            "score": {"type": "integer"},
            "verdict": STR,
            "requirements": {"type": "array", "items": _obj({"requirement": STR, "level": {"type": "string", "enum": ["STRONG", "PARTIAL", "GAP"]}, "note": STR})},
            "unique_strengths": STRS,
            "gaps": STRS,
            "emphasize": STRS,
            "angle": STR,
            "domain": STR,
            "experience_ranking": {"type": "array", "items": _obj({
                "experience": STR, "kind": {"type": "string", "enum": ["experience", "leadership", "project"]},
                "score": {"type": "integer"}, "include": {"type": "boolean"}, "how": STR})},
            "jd_keywords": STRS,
        }),
    )
    result["verdict"] = _no_em_dash(result["verdict"])
    return result


TAILOR_RULES = """How to tailor: REFRAME, don't invent.
0. DOMAIN KNOWLEDGE IS A TOP PRIORITY. Identify the company's industry/domain (fintech, gaming, healthcare, edtech,
   consumer social, logistics, ...). Use my 'Domain map' to: (a) prefer same-domain projects/experiences when choosing
   what goes in (e.g. a gaming project for a gaming company, health-data work for health tech); (b) use the domain's
   vocabulary in bullets where it honestly describes what I did; (c) when the JD is domain-specific, add a
   'Domain Knowledge:' line to Skills listing ONLY domains my materials prove (plus any company cert marked in progress).
   In `changes`, name the domain and the domain proof you surfaced.
1. Decide the role family this JD really is (data analyst, product analyst, PM, product ops, marketing analytics,
   data science, AI automation, digital transformation, tech/AI consulting, ...) and pick the ANGLE: which part of
   my story is the strongest truthful pitch for it.
2. For each role, choose the best bullets from ALL my versions and narratives for that angle. You may rewrite a
   bullet's wording to lead with the transferable skill this role family cares about (e.g. the same project framed
   as stakeholder insight for marketing, as automation for AI roles, as user/product impact for PM). Every fact,
   tool and number must be backed somewhere in my materials. Never invent numbers, tools, scope or outcomes.
3. Job titles: use a title for that role as written in my materials. If my versions use different titles for the
   same role, you may pick the best fitting one. Never make up a new title.
4. Projects: pick the ones that prove the angle; drop the rest.
5. Use the JD's vocabulary where it honestly describes what I did (helps ATS), but don't keyword-stuff.
6. Skills: select and order for this role family. Only skills that appear in my materials.
7. ONE PAGE, NON-NEGOTIABLE. Space budget for my layout (letter, 10.5pt):
   - Experience + Leadership + Projects together: AT MOST 12 bullets. Max 3 bullets per role, EXACTLY 1 per project
     (unless my profile/playbook allows more for a specific project, or I explicitly asked to expand one).
   - At most 4 entries under Experience/Leadership and at most 3 projects. Fewer, stronger entries beat more entries.
   - Every bullet ends near the right margin: ~105-125 characters (1 full line) or ~215-245 (2 full lines). Never
     ~130-200 (a half-empty last line). See my RESUME PREFERENCES; they are mandatory.
   - Skills: 4-5 curated lines, ~5-8 strong JD-relevant items each, no near-duplicates; NOT cluttered (a skills
     line may end before the margin). Coursework: 1 full line.
   HOW TO CHOOSE (score to win): list every candidate bullet from all my versions, score each on (a) how many of this
   JD's must-have keywords/skills it proves, (b) strength of the concrete result/number, (c) recency and relevance of the
   role. Keep the top scorers within the budget; drop the rest (mention big drops in `changes`). Put the highest-scoring
   bullet first in each role. Write each bullet as: strong verb + what I did using the JD's words + measurable result.
8. TAILOR EDUCATION EXTRAS FOR EVERY JOB: Coursework = the 4-7 courses from my materials most relevant to this JD (one
   line); Certificates = the relevant ones I hold plus any (in progress) per the certificate rules. School, degree and
   dates stay factual. Contact line must stay ONE line (the app removes GitHub for non-technical roles).
9. Retrieval-Augmented Generation (RAG): spell it out in EVERY bullet that mentions it (Skills may say RAG). Bold the
   key numbers and key tech inside bullets; never bold the GPA or whole lead-in phrases. No em dashes. Hyperlink the
   company/project NAME, never print "Link" or a raw URL. Projects go under a "Project" heading, never under Leadership.
10. NO ITALICS anywhere (no \\textit, \\emph, or *single asterisks*); bold is fine. Action verb first, concrete result, ~1.5 lines max per bullet.
11. If the JD wants something I genuinely haven't done, do NOT add it. List it in gaps_not_added.
In `changes`, first state the role family + angle you chose, then each notable reframe and which JD requirement it
serves, so I can sanity-check truthfulness."""

ATS_RULES = """ATS (applicant tracking system) optimization, all truthful:
- Mirror the JD's exact wording for skills, tools and responsibilities wherever it honestly describes my work
  (e.g. JD says "stakeholder management" and I "worked with stakeholders" -> use their phrase).
- Every hard skill / tool the JD lists that I actually have must appear somewhere (bullets or Skills), spelled like the JD.
- Include the JD's role keyword naturally (e.g. "product analytics", "business intelligence") in bullets that support it.
- Standard section headings (Education, Experience, Projects, Skills), plain text, no images/icons/columns."""


def variant_note(variant: str, strategy: str, email: str) -> str:
    return (f"\n\nTHIS IS RESUME VERSION {variant}. Strategy: {strategy}\n"
            f"Contact email for this version: {email or '(keep as is)'}.\n{ATS_RULES}")


ENTRY = _obj({"heading": STR, "subheading": STR, "date": STR, "location": STR, "bullets": STRS})
RESUME_SCHEMA = _obj({
    "name": STR,
    "contacts": STRS,
    "sections": {"type": "array", "items": _obj({"title": STR, "lines": STRS, "entries": {"type": "array", "items": ENTRY}})},
})


def tailor_resume(job: dict, note: str = "") -> dict:
    """Template mode: structured content that app/latex.py renders. Nothing here can break LaTeX."""
    result = _call(
        f"""{_me_block()}

{_job_block(job)}

Tailor my master resume to THIS job.

{TAILOR_RULES}{note}

Output format:
- `resume.contacts`: short items like "City, ST", "me@x.com", "linkedin.com/in/me", "github.com/me".
- `resume.sections`: in resume order (e.g. Education, Experience, Projects, Skills). Experience/Projects/Education
  use `entries` (heading = company or project, subheading = title or tech stack, date, location, bullets) and
  empty `lines`. Skills uses `lines` like "**Languages:** Python, TypeScript" and empty `entries`.
- Plain text only, no LaTeX. Use **double asterisks** for bold (metrics/technologies) if my resume bolds them.""",
        _obj({"resume": RESUME_SCHEMA, "changes": STRS, "jd_keywords": STRS, "gaps_not_added": STRS, "stretch_skills": STRS, "certs_to_start": STRS}),
        effort="high",
        task="writing",
    )
    return result


def content_to_tex(base_tex: str, resume: dict, job: dict) -> dict:
    """Technical half of the OpenAI/Claude split: put already-written content into my LaTeX layout, verbatim."""
    return _call(
        f"""<MY LATEX RESUME (layout/template; its current content is just an old version)>
{base_tex}
</MY LATEX RESUME>

<FINAL RESUME CONTENT (already tailored for {job['role']} at {job['company']}; JSON)>
{json.dumps(resume, ensure_ascii=False, indent=1)}
</FINAL RESUME CONTENT>

Write the FINAL RESUME CONTENT into my LaTeX layout and return the complete .tex.
- Keep my preamble, packages, custom macros and formatting conventions exactly; use my macros the way the file does.
- Use the content's wording, order, sections and dates EXACTLY. Do not rephrase, add, or drop anything.
- HEADER: keep my file's header block (name line + contact line) exactly as it is in my file, character for character.
- Bold the key numbers/metrics and key tech in bullets the way my file does (\\textbf). NEVER bold the GPA. No italics.
- LINKS: never print the word "Link" or a raw URL. If an entry's heading includes a URL (or "| Link" with a URL in my
  materials), make the company/project NAME a hyperlink the way my file does (\\href{{url}}{{\\underline{{Name}}}}).
  If there's no URL, just print the name.
- Escape %, &, _, #, $ in text. Don't add packages. The file must compile as-is.""",
        _obj({"tex": STR}),
        effort="medium",
        max_tokens=32000,
    )


def tailor_own_tex(job: dict, base_tex: str, note: str = "") -> dict:
    """Your-own-.tex mode: my LaTeX file is the LAYOUT (preamble, macros, section style). The content is
    re-picked and reframed from all my resume versions + narratives for this job's role family."""
    return _call(
        f"""{_me_block()}

<MY LATEX RESUME (the layout/template to keep; its current content is just one version)>
{base_tex}
</MY LATEX RESUME>

{_job_block(job)}

Produce my tailored resume for THIS job as a complete .tex file in exactly my LaTeX layout.

{TAILOR_RULES}{note}

LaTeX rules:
- Keep my preamble, packages, custom macros, section order style and formatting conventions exactly.
  Only change the content inside them (entries, bullets, skills). Use my macros the same way the file does.
- Escape %, &, _, #, $ in any text you write. Don't add packages. The file must compile as-is.
- If it's a template with placeholder content, fill it with my real content from the materials above.""",
        _obj({"tex": STR, "changes": STRS, "jd_keywords": STRS, "gaps_not_added": STRS, "stretch_skills": STRS, "certs_to_start": STRS}),
        effort="high",
        max_tokens=32000,
    )


COACH = """You are my resume coach for THIS job, working with me in a chat. Your job: get the strongest TRUTHFUL
resume for this role, by (a) finding gaps between what the JD needs and what my materials show, and (b) asking me
about them, because I often did things I never wrote down.

How to ask (keep it effortless to answer):
- At most 3 questions per turn, each tied to a specific role/project of mine and a specific JD need.
  Good: "At <Company>, did you ever share findings with marketing or sales? Even one deck or Slack summary counts."
  Bad: "Tell me about your communication skills."
- Make them quick to answer: yes/no plus one detail (what, who for, any number).
- Don't re-ask things already covered in my materials or earlier in this chat.

How to handle my replies:
- If I give an instruction (include this role, frame it as X, drop Y, shorten, emphasize Z), follow it within truthfulness.
- Anything I tell you in this chat about what I did is true. Record each new fact in `new_facts` as one line
  "<Role> @ <Company>: <fact>" so I can save it to my narratives.
- Set `update_resume` true when you have something worth changing or I asked for a change, and return the FULL
  updated resume. Otherwise false and return the resume unchanged.
- Never invent anything I didn't say or that isn't in my materials. If a gap is real, say so plainly and suggest
  the closest honest framing.
- `reply`: short and friendly, what you changed (if anything) and why, then your questions. No em dashes."""


def resume_chat(job: dict, transcript: list[dict], message: str, current: str, own_tex: bool, note: str = "") -> dict:
    convo = "\n\n".join(f"{'ME' if t['role'] == 'me' else 'COACH'}: {t['content']}" for t in transcript)
    opener = (message.strip() or
              "Start: tell me the role family + angle you'd use, then ask me your top gap questions.")
    own_tex = own_tex and WRITER != "openai"  # OpenAI writes content only; Claude turns it into LaTeX
    out_rules = ("Return `tex`: the full updated .tex in the SAME layout (keep preamble/macros; escape %, &, _, #, $), "
                 "or '' when update_resume is false.") if own_tex else (
                 "Return `resume` in the structured format (sections with entries or lines, **bold** allowed, no LaTeX). "
                 "When update_resume is false, return the current resume content restructured faithfully.")
    prompt = f"""{_me_block()}

{_job_block(job)}

<CURRENT TAILORED RESUME FOR THIS JOB>
{current or '(none yet, build the first version when ready)'}
</CURRENT TAILORED RESUME FOR THIS JOB>

{COACH}

{TAILOR_RULES}{note}

<CHAT SO FAR>
{convo or '(new chat)'}
</CHAT SO FAR>

ME (now): {opener}

{out_rules}"""
    base = {"reply": STR, "questions": STRS, "new_facts": STRS, "update_resume": {"type": "boolean"}, "changes": STRS,
            "stretch_skills": STRS, "certs_to_start": STRS}
    base.update({"tex": STR} if own_tex else {"resume": RESUME_SCHEMA})
    result = _call(prompt, _obj(base), effort="high", max_tokens=32000, task="writing")
    result["reply"] = _no_em_dash(result["reply"])
    return result


def fit_one_page(tex: str, pages: int, job: dict, attempt: int) -> dict:
    """The PDF came out longer than one page: cut the lowest-scoring content until it fits."""
    cut = "the SINGLE next item" if attempt <= 3 else "the next two items"
    return _call(
        f"""{_job_block(job)}

{profile.playbooks_block()}

<RESUME .tex THAT COMPILES TO {pages} PAGES>
{tex}
</RESUME>

This resume is {pages} pages. It must be ONE page, but cut as LITTLE as possible (white space at the bottom is also bad).
This is attempt {attempt}: remove {cut} and nothing else, then I recompile and tell you if more is needed:
0. If my PLAYBOOK for this role family gives a cut order, take the next item in that order.
1. Otherwise: the lowest-scoring bullet for this JD (weakest keyword match + weakest result); only drop a whole
   entry if no single bullet is left to drop; or shorten one long bullet by one line.
2. Never drop the most recent role or the strongest JD-matching bullet. Don't touch the preamble, macros or header.
3. Don't add anything new. Keep all LaTeX valid (escape %, &, _, #, $).
Return the full edited .tex and a short list of what you cut.""",
        _obj({"tex": STR, "cut": STRS}),
        effort="medium",
        max_tokens=32000,
    )


def fill_lines(tex: str, issues: list[dict], job: dict) -> dict:
    """Remove white space on the right: rework ONLY the bullets/lines that end short, keeping one page."""
    listing = "\n".join(f"- line ending short ({int(i['fill'] * 100)}% full): \"{i['line'][:120]}\" "
                         f"(continues from: \"{i['previous'][:80]}...\")" for i in issues)
    return _call(
        f"""{_me_block()}

{_job_block(job)}

<RESUME .tex (one page)>
{tex}
</RESUME>

These printed lines END SHORT, leaving white space on the right (text extracted from the PDF; word order may be jumbled):
{listing}

Fix ONLY the bullets / lines these belong to, so every line ends near the right margin:
- A bullet whose last line is short: either tighten it to exactly one fewer full line, or add one true, specific detail
  from my materials so the last line is nearly full. Prefer tightening if the page is crowded.
- A coursework line that spills a word or two: swap in a shorter JD-relevant course or drop the least relevant one so
  it fits on one line. Skills lines must stay curated (5-8 items, no clutter); only fix one that wraps.
- Same facts and numbers. Don't touch other bullets, the header, macros or spacing. Keep it ONE page. Valid LaTeX.
Return the full edited .tex and a short list of what you changed.""",
        _obj({"tex": STR, "changed": STRS}),
        effort="medium",
        max_tokens=32000,
    )


def add_content(tex: str, free: float, job: dict) -> dict:
    """Empty space at the bottom: add the strongest relevant content from my materials to fill it."""
    return _call(
        f"""{_me_block()}

{_job_block(job)}

<RESUME .tex (one page, but about {free:.0f} empty lines at the bottom)>
{tex}
</RESUME>

There are about {free:.0f} empty lines at the bottom of the page. Fill them with the STRONGEST content for THIS job from my
materials (true facts only), about {max(int(free) - 1, 1)} lines in total, so the page ends near the bottom but stays ONE page:
- NEVER add a second bullet to a project (projects have exactly 1 bullet). Best options, in order: a high-impact JD-relevant bullet for an existing role (from my other resume versions or
  narratives), a same-domain project (Domain map) with 1-2 bullets, or more JD-relevant skills on a short skills line.
- Prefer the niche / personality points in my RESUME PREFERENCES when they fit this JD.
- Follow my playbook if one applies (its fixed bullets stay; you may ADD, not reword). Every new line must end near the
  right margin (no half-empty last lines). Don't touch the header, macros or spacing. Valid LaTeX.
Return the full edited .tex and a short list of what you added.""",
        _obj({"tex": STR, "added": STRS}),
        effort="medium",
        max_tokens=32000,
    )


def review_layout(png_path: str) -> dict:
    """Look at the rendered resume like a recruiter would: spacing / proportion / consistency problems only."""
    import base64
    img = base64.b64encode(open(png_path, "rb").read()).decode()
    return _call(
        [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
         {"type": "text", "text": """This is a one-page resume. Review ONLY the visual layout, like a picky designer:
consistency of spacing between sections, between entries, between a heading and its first bullet, line wraps that leave
a word alone on a line, proportions (name size vs body, section heading size), alignment, crowding vs white space, and
anything that looks inconsistent. Don't comment on wording or content. Score 1-10 and list concrete issues, each with
where it is and what to change (e.g. 'gap above Leadership is ~half the gap above Project')."""}],
        _obj({"score": {"type": "integer"}, "issues": STRS, "looks_good": STRS}),
        effort="medium", max_tokens=4000)


def extract_person(page_text: str, url: str) -> dict:
    """Read the top of a LinkedIn profile page (what the side panel sees) into fields."""
    return _call(
        "This is the visible text of a LinkedIn profile page. Extract who this person is. Use '' / 0 when unknown.\n"
        "degree: 1, 2 or 3 from the connection badge (\"1st\", \"2nd\", \"3rd+\"), 0 if not shown.\n"
        "company/title: their CURRENT job. school: most recent school. past_companies: earlier employers.\n"
        "shared: anything the page says we have in common (mutual connections, same school, etc.).\n\n"
        f"URL: {url}\n<PAGE>\n{page_text[:6000]}\n</PAGE>",
        _obj({"name": STR, "headline": STR, "title": STR, "company": STR, "location": STR, "degree": {"type": "integer"},
              "school": STR, "past_companies": STRS, "shared": STR}),
        effort="low",
        max_tokens=4000,
    )


# ---- outreach ---------------------------------------------------------------------------
# Recruiting OS drafting.js: follow-up #1 adds ~22% response rate, #2 ~11%, #3 ~3%. Tone shifts per tier.
TIER_GUIDANCE = {
    1: "Gentle nudge. Assume they just haven't seen it yet, keep it light and short.",
    2: "Direct but polite. Reference that you reached out before, ask for one specific next step.",
    3: "Final low-pressure check-in. Explicitly give them an easy out (\"no worries if the timing isn't right\"). Very short.",
}


def escalation_tier(days_since_last_message: int) -> int:
    if days_since_last_message >= 11:
        return 3
    if days_since_last_message >= 4:
        return 2
    return 1


KINDS = {  # order = order in the UI dropdown
    "peer_congrats": "SHORT note to an early-career person (intern, new grad, recently started). Under 70 words. "
                     "Open with a specific compliment and congrats on their new role/offer (from their title/profile), "
                     "then say what I'm pursuing and ask for a couple of questions, 'either here or on a quick 15-minute "
                     "call, whichever you prefer'. {calendly_hint} End with a warm thanks. Follow my 'Early-career person' "
                     "template closely.",
    "alumni": "Short note to a fellow {school} alum. Under 60 words. Open with the shared school, name their role and "
              "company, ask to learn about their experience, 'Are you free to speak in the coming weeks?' {calendly_hint}",
    "connected_pitch": "They just accepted my connection request. Follow my 'After they accept my request' template: "
                       "thank them for connecting; one specific thing about their path that impressed me plus a curious "
                       "question about it; who I am in one or two lines TAILORED to this role and to them (pick the 1-2 most "
                       "relevant things from my background); where I am with this company (applied, or planning to apply); "
                       "the honest line that I'm not sure my experience alone will land an interview; ask to hear about "
                       "their journey, especially how they prepared for something specific to this role; {calendly_line} "
                       "Sign 'Best, {first_name}'. Under 150 words.",
    "connection_note": "LinkedIn connection-request note. HARD LIMIT {limit} characters including spaces. "
                       "One specific hook + one tiny ask. No greeting fluff.",
    "referral_ask": "Direct referral ask for a POSTED role. Under 110 words. Name the exact role (and link/job ID if I have "
                    "it). Ask if they'd be open to referring me or helping me stand out so I can get an interview and talk "
                    "with the team to see if I'm a fit. One line on why I'm genuinely passionate about this team/product "
                    "(specific) and my strongest relevant proof point. 'Let me know if any material would help (resume, a "
                    "short blurb you can paste).' Keep it low-pressure: 'a coffee chat is totally open too.' {calendly_hint}",
    "recruiter_after_apply": "Short note to a recruiter right after I applied. Under 90 words. Name the exact role, "
                             "one line on why I'm a strong fit with a concrete number, ask if they're the right person.",
    "hiring_manager": "Intro note to the likely hiring manager (job-analyzer intro structure): warm opener, who I am + headline "
                      "number, 2-3 relevant technical areas, then TWO sentences on why this team: first what their people/users "
                      "actually face with real stakes, second what I bring to that named team. Close simply. 80-100 words.",
    "cold_dm": "Cold LinkedIn DM / email to someone I don't know. 3-5 sentences, under 120 words. Open with the specific "
               "personalization detail, not a generic greeting. Clearly and briefly state the ask (advice, a short chat, a "
               "referral only if it comes up naturally) without being pushy.",
    "follow_up": "Follow-up to someone who hasn't replied. This is tier {tier} of 3. {tier_guidance} Under 80 words. "
                 "Must NOT repeat the first message's phrasing, it should read like a distinct, brief nudge.",
    "thank_you": "Thank-you note after they replied / chatted / referred me. Specific about what helped. Under 70 words.",
}


# When the role is already posted, the ask gets direct (my words). Applies on top of the message type.
DIRECT_KINDS = {"peer_congrats", "alumni", "connected_pitch", "cold_dm", "connection_note", "hiring_manager"}
DIRECT_MODE = ("The role IS POSTED, so be DIRECT (keep the message type's tone and length): name the exact role, say I "
               "applied or am applying (per Status), and ask plainly whether they'd be open to referring me or helping me "
               "stand out so I can get an interview and talk with the team to see if I'm a fit. Show I'm genuinely "
               "passionate about something specific to this team. Offer 'let me know if any material would help' and "
               "keep 'a coffee chat is totally open' as the softer option. For a connection note, compress this into "
               "the character limit.")

LANGUAGES = {"en": "Write in English."}  # more come from profile/languages.json (private)


def languages() -> dict:
    return {**LANGUAGES, **{k: v.get("instruction", "") for k, v in profile.languages().items()}}


def draft_message(job: dict, person: dict, kind: str, personalization: str = "", tier: int = 1,
                  previous_message: str = "", language: str = "en", not_open: bool = False) -> dict:
    if kind not in KINDS:
        raise AIError(f"unknown message kind: {kind}")
    me = profile.me()
    limit = int(me.get("connection_note_limit") or 200)
    cal = (me.get("calendly_url") or "").strip()
    instructions = KINDS[kind].format(
        limit=limit, tier=tier, tier_guidance=TIER_GUIDANCE.get(tier, ""),
        school=me.get("school") or "my school", first_name=((me.get("name") or "").split() or ["me"])[0],
        calendly_hint=f"Offer my Calendly for the call: {cal}" if cal else "",
        calendly_line=f"then 'My availability is listed here: {cal}'" if cal else "then offer a quick 15-minute call")
    voice = profile.real_or_blank("voice")
    resume = profile.real_or_blank("resume")

    prompt = f"""Write a message from me to {person['name']}.

<ME>
Name: {me.get('name') or '(my name)'}
Headline: {me.get('headline')}
School: {me.get('school')}  Past employers: {', '.join(me.get('past_employers') or [])}
{('<MY RESUME>' + chr(10) + resume + chr(10) + '</MY RESUME>') if resume else ''}
</ME>

<MY VOICE (match this closely, it matters more than polish)>
{voice or 'Casual but respectful, short sentences, specific, no fluff.'}
</MY VOICE>

<THEM>
Name: {person['name']}
Title: {person.get('title') or '?'} at {person.get('company') or job['company']}
How I know them / relationship: {person.get('relationship') or ('1st-degree LinkedIn connection' if person.get('degree') == 1 else 'I do not know them yet')}
Notes: {person.get('notes') or ''}
Why they're a good person to ask: {'; '.join(person.get('reasons') or [])}
</THEM>

<THE JOB I'M GOING FOR>
{job['role']} at {job['company']} {('(' + job['url'] + ')') if job.get('url') else ''}
Status: {job.get('status')}
{"The role is NOT OPEN YET: I'm reaching out early to learn and get on their radar before it posts. Say I'm planning to apply / interested in opportunities there next year; do NOT say I applied." if not_open else DIRECT_MODE if (job.get("url") and kind in DIRECT_KINDS) else ""}
</THE JOB I'M GOING FOR>

{('Angle to pitch me with for this role: ' + job_angle(job)) if job_angle(job) else 'Pitch me using the transferable skills that matter most for this role family (see my resume versions), not my past job titles.'}
Personalization / reason I'm reaching out to them specifically: {personalization or '(none given, use the strongest real signal above; do not invent one)'}
{('Previous message I sent them:' + chr(10) + previous_message) if previous_message else ''}

Message type: {instructions}
Language: {languages().get(language, LANGUAGES["en"])}

Rules:
- Sound like ME (see voice). First person, plain, human.
- Do not use the phrase "pick your brain". No "I hope this finds you well".
- Do not fabricate anything about them or me beyond what's given.
- Leave [brackets] only for things I must fill in myself.
- `draft` is the exact text to paste. `subject` only if this reads like an email, else ''.
- `why_this_works`: one line so I learn the pattern."""

    result = _call(prompt, _obj({"draft": STR, "subject": STR, "why_this_works": STR}), effort="medium", max_tokens=4000,
                   task="writing")
    result["draft"] = _no_em_dash(result["draft"])
    if kind == "connection_note" and len(result["draft"]) > limit:
        result["warning"] = f"{len(result['draft'])} chars, over your {limit}-char limit. Trim before sending."
    return result


def batch_connection_notes(job: dict, people: list[dict]) -> list[dict]:
    """One call, a connection note per person: for firing off requests to everyone worth knowing at a company."""
    me = profile.me()
    limit = int(me.get("connection_note_limit") or 200)
    voice = profile.real_or_blank("voice")
    roster = "\n".join(
        f"- id={p['id']} | {p['name']} | {p.get('title') or '?'} | why: {'; '.join(p.get('reasons') or []) or 'works there'}"
        for p in people)
    result = _call(
        f"""I'm applying to {job['role']} at {job['company']} and sending LinkedIn connection requests to people there.
Write one connection note per person below, each UNDER {limit} characters including spaces.

About me: {me.get('headline')} | school: {me.get('school')} | past: {', '.join(me.get('past_employers') or [])}
<MY VOICE>
{voice or 'Casual but respectful, short, specific.'}
</MY VOICE>

People:
{roster}

Rules: each note uses that person's strongest real hook (shared school/employer, same role, recruiter). Mention I'm
interested in the {job['role']} role. Vary the openings so they don't read like a template. No "pick your brain", no em dashes,
don't invent anything about them.""",
        _obj({"notes": {"type": "array", "items": _obj({"id": {"type": "integer"}, "note": STR})}}),
        effort="low",
        max_tokens=8000,
        task="writing",
    )
    notes = [{"id": n["id"], "note": _no_em_dash(n["note"])} for n in result["notes"]]
    for n in notes:
        n["over_limit"] = len(n["note"]) > limit
    return notes
