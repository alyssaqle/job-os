# Job OS

A local, agentic job-search workflow: a FastAPI app, a Chrome side panel, and Claude Code skills that read the same
declarative profile files. Designed for low cognitive load: **one next action at a time, nothing to paste, nothing to
log by hand.**

```
find a role ──► tailored resume PDF ──► apply (Simplify) ──► message the right people ──► follow up
   (any tab)       one click in the         auto-detected         ranked by who's most likely     reminded
                   side panel               "applied"             to reply, drafted in your voice automatically
```

Everything runs locally. Your data lives in `data/jobos.db` and your profile in `profile/`; both are gitignored, and
only blank templates are committed. Model calls go to the Claude API (and optionally the OpenAI API).

## How it works

| Layer | What it does |
|---|---|
| **Intake** | Chrome MV3 side panel reads the job page you're on and saves it with one click |
| **Model routing** | Language work (bullet wording, messages) can go to OpenAI; LaTeX generation, fit checks, profile extraction and a vision-based layout review go to Claude. All calls use JSON-schema structured outputs. |
| **Declarative rules** | Markdown profile files (`resume-preferences.md`, role playbooks `playbook-*.md`, `voice.md`) steer every call, so behavior changes without code changes. A source-precedence order resolves conflicts between old and new facts. |
| **Grounding** | Tailoring may only use facts from your own profile files; `profile/fact-fixes.json` (private) holds corrections that are re-applied on every build |
| **Layout engine** | Compiles LaTeX, measures the PDF (free space, half-empty lines, section gaps) and adjusts spacing until the page is exactly full |
| **Referral ranking** | Weighted scoring over a LinkedIn connections export plus profiles read in the side panel: degree, shared background, tie strength (inverted U), seniority, with reasons shown |
| **Guardrails** | Never auto-sends; a work-authorization filter (driven by `visa_status` in your profile) flags postings you can't take |

## Setup (one time, ~15 min)

1. **API key:** `cp .env.example .env` and paste your Anthropic API key into `ANTHROPIC_API_KEY=`.
2. **Start it:** `./run.sh`. It opens http://localhost:8000. Keep that terminal open.
3. **Tell it about you** (the **Me** tab):
   - *About me*: school, past employers, clubs/programs, target roles. These are what it ranks people by.
   - *resume*: paste your **whole** master resume/CV: every role, project and bullet.
   - *experience*: the longer story and metrics behind each bullet (optional, makes tailoring better).
   - *voice*: how you write. Paste 3-5 real messages you sent that got replies. This matters most for outreach.
   - Already have a LaTeX resume you love? Save it as `profile/resume.tex` and tailoring edits *that* file instead of using the built-in template.
4. **Bring in your network** (the **People** tab): LinkedIn → Settings → Data privacy → *Get a copy of your data* → *Connections*. Import the `Connections.csv` it emails you. Have a referral spreadsheet? Export it to CSV and import it too.
5. **Install the side panel:** Chrome → `chrome://extensions` → turn on *Developer mode* → *Load unpacked* → pick the `extension/` folder. Pin it. **Alt+J** opens it.

## Daily flow

**Everything happens in the side panel, next to the page you're already on.**

| You're on… | The panel shows | You click |
|---|---|---|
| A job posting (LinkedIn, Greenhouse, Lever, Ashby, Workday, Jobright, anything) | **Save + tailor my resume** | 1 click. It reads the JD off the page and builds `Your_Name_Resume_Company.pdf` |
| The same job, tailored | 1 ✓ Resume · **2 Apply** · 3 Reach out | **Download**, then let Simplify fill the form and upload that PDF |
| The "thanks for applying" page | *"✓ Marked applied"* (automatic) | nothing |
| Back on the job | **3 Reach out**: top people, ranked | open a profile |
| Someone's LinkedIn profile | who they are, which of your jobs they help with, the right message type | **Write it in my voice**, Copy, paste into LinkedIn, Send |
| (you clicked Send / Connect on LinkedIn) | *"✓ Logged"* (automatic) | nothing |
| They accepted your request | Next Up: *"Jane accepted! Send your pitch"* | open it, and the pitch DM is pre-selected |
| Anything else | **Next up**: the single most important thing | it |

The **dashboard** (localhost:8000) is the big-picture view: every role in one table, how many people you have at each company, who you've messaged, and follow-ups due. Click a row for Resume / People / Fit / Log.

### Resume chat (per job)

Dashboard → click a role → **Resume** → **Find my gaps for this job**. A coach compares the JD against *all* your resume versions and stories, then asks up to 3 quick, specific questions ("At Intuit, did you ever share findings with marketing?"). Answer in a few words, or give instructions ("include my lab role but frame it as product analytics"). It rebuilds the PDF when there's something worth changing. Anything new you tell it shows up as **New things I learned about you**; one click saves it to `profile/experience.md`, so every future resume knows it too.

Your master resume can be messy: paste every version you have plus the story behind each role. Tailoring picks the role family (analyst, PM, product ops, AI automation, consulting, …), chooses the angle, and reframes bullet wording for it, using only facts that appear somewhere in your materials.

### Which message it drafts

- **Not connected yet** → connection-request note (under your character limit: 200 free, 300 Premium; set it in *Me*). Need to hit many people at one company? Use **Connection notes for top people (batch)**.
- **Already connected / accepted / important person** → *"why I fit + curious about you"* DM: sells you for that team and JD, **and** asks about their path, because people reply to genuine interest.
- Also available: referral ask, recruiter "I just applied", hiring-manager intro, cold DM/InMail, 3-tier follow-ups (tone escalates, the last one gives them an easy out), thank-you.

### Who it ranks first (and why)

Every person gets a score with the reasons shown: referral-sheet person > 1st-degree > shared school/employer/club > reachable engineers & recruiters (VPs rarely reply) > same role as the job. Relationship strength follows an **inverted U**: people you've had a few real touches with rank above both strangers and your closest contacts, because that's who actually passes along jobs (Rajkumar et al., *Science* 2022, the LinkedIn weak-ties experiment).

## One laptop or two monitors?

It's built so **one laptop works**: the side panel means the job page, Simplify, and your resume and messages share one window. No tab-hunting.

With two monitors:
- **Left:** browser with the job site / LinkedIn + side panel (where you *act*).
- **Right:** the dashboard (where you *see progress*: the Next Up card and the table).

Rules the design follows (so you can keep them too):
- **One next action, not a list.** Next Up shows one big card, and the rest are collapsed. "Not now" is always allowed.
- **Nothing to remember.** Applied, requested, and messaged get logged by what you already click, and follow-ups get scheduled automatically (day 4).
- **Batch similar work.** Tailor + apply several roles, then do one outreach pass with batch notes. Switching task *types* is what drains you, not the number of tasks.
- **Visible progress.** Steps 1-2-3 turn green, and the table shows "Reached" counts.

## Finding roles fast

- **Me tab → Find new roles**: LinkedIn job searches for each target role, *past 24h, newest first* (SnipeDin's URL builder).
- In Claude Code, from this folder: `/job-search` (LinkedIn/HN/X with connection insights), `/job-crawler <careers page>` (best 3 roles for you at a company), `/network-finder <company>`, `/job-analyzer <url>`, `/resume-tailor`. These are the original skills, copied in `.claude/skills/`.

## Honest limits

- **It never clicks Send for you.** Auto-sending on LinkedIn gets accounts restricted. It drafts, you paste and send, and it logs automatically. Also note LinkedIn caps invitations (roughly 100/week for most accounts), so spend them on the top-ranked people.
- Auto-detection reads page text, so it can miss on unusual sites. The **I applied** / **I sent it** buttons are the backup.
- Profile reading uses Claude on the visible page text, one call per new profile (cached per session).

## Where the ideas and code came from

All MIT-licensed. Licenses are in `third_party/`.

| Repo | What we took |
|---|---|
| [ai-job-application-kit](https://github.com/AjinkyaPawale1/ai-job-application-kit) | `CLAUDE.md` guardrails (never fabricate, no em dashes), profile templates in `profile/`, skills `resume-tailor`, `job-apply`, `job-search`, `job-preferences` (the last three from [neonwatty/job-apply-plugin](https://github.com/neonwatty/job-apply-plugin)) |
| [job-search-skills](https://github.com/sameergdogg/job-search-skills) | skills `network-finder`, `job-analyzer`, `job-crawler`, `job-form-filler`; the 1st-degree LinkedIn search URL; referral-sheet-first ranking; fit rubric (STRONG / PARTIAL / GAP); intro-email structure |
| [SnipeDin](https://github.com/1Mangesh1/snipedin) | LinkedIn job-search URL builder (`app/linkedin.py`) |
| [Recruiting OS](https://github.com/esaba12/recruiting-tool) | tie-strength scoring and reachability (`app/warmpaths.py`), referral coverage, "what needs attention" queue (`app/nextup.py`), outreach prompts and follow-up escalation tiers (`app/ai.py`) |

## Two models: OpenAI writes, Claude builds (optional)

Add to `.env` and restart:
```
JOBOS_WRITER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5
```
- **OpenAI (language):** resume wording and reframing, resume chat, outreach messages, batch connection notes.
- **Claude (technical):** putting content into your LaTeX layout, one-page fitting, reading job pages / LinkedIn profiles, fit checks, work-authorization backup check.

Remove `JOBOS_WRITER` (or set it to `claude`) to go back to Claude for everything.

## Privacy

Committed: code, tests, blank `profile/*.template.*` files. Never committed (gitignored): your real profile files,
`data/` (jobs, contacts, tailored PDFs), `sources/`, `.env`. Optional private configs: `profile/languages.json` (extra
outreach languages and greetings) and `profile/fact-fixes.json` (your corrections).

## Develop

```
./run.sh                      # server with auto-reload
.venv/bin/python -m pytest    # tests (no API calls)
```

`app/main.py` API · `app/ai.py` Claude prompts · `app/warmpaths.py` ranking · `app/latex.py` PDF · `app/nextup.py` queue · `extension/` Chrome side panel.
