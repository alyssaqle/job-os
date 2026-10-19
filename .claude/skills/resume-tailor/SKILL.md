---
name: resume-tailor
description: Tailor your LaTeX resume to a specific job description with minimal, targeted edits and compile a PDF. Use when the user pastes a job URL or JD and explicitly asks to tailor/customize the resume for that role (not on every application).
allowed-tools: Read, Write, Edit, Bash, WebFetch, mcp__playwright__*
---

# Resume Tailor

Tailor the user's LaTeX resume to a SPECIFIC job description with a few surgical edits, then compile a PDF. This is a companion to the job-search and job-apply skills. Invoke it selectively, only when the user explicitly asks to tailor or customize their resume for a role, not automatically on every application.

## Canonical files

- Base resume (source of truth, never edit in place): `sources/resume.tex`. Some users keep their master resume elsewhere; if so, point the skill at that path instead, but still treat it as read-only.
- Tailored output directory: `sources/tailored/` (create it if it does not exist).
- Compiler: `tectonic` (offline, local, no network needed). If it is missing, install with `brew install tectonic`.
- Every run starts from a FRESH copy of the base resume. Never accumulate edits across jobs.

## Workflow

1. Get the JD. Try `WebFetch` on the URL first. If the page is JavaScript-gated (LinkedIn, Workday, Ashby, Greenhouse, and similar), use Playwright MCP instead: `browser_navigate` then `browser_snapshot`. If the user pasted the JD as text, use that directly. Extract the role title, must-have skills, key responsibilities, named technologies, the domain, and recurring keywords.

2. Decide what to change. THE CORE RULE, be conservative: make targeted, minimal edits. Per experience block, the hard ceiling is swapping about 2 bullets (remove up to 2 weaker bullets, add up to 2 that match the JD). Do not rewrite whole blocks or touch every bullet. Use generic routing logic to place new emphasis where it is truthful and natural:
   - Route modern, most-relevant framing to the most recent role.
   - Route platform, infrastructure, or scaling emphasis to a role that genuinely involved it.
   - Route research or analytics emphasis to a research role.
   Skills section: you may reorder it or add 1-3 JD keywords ONLY if the candidate plausibly has them. Never fabricate a tool they have not used. Leave Education alone.

3. Hard constraints.
   - Every added bullet must be truthful and consistent with the real project it sits under.
   - If the JD wants something the candidate genuinely has not done, do NOT add it. Note the gap instead.
   - Keep the resume to one page.
   - No em dashes.
   - Preserve the existing `\textbf{}` bolding convention for metrics and technologies.
   - Match the existing bullet style: action verb first, concrete metric, about 1.5 lines maximum.
   - Do not invent numbers that contradict the existing resume.

4. Apply edits. Copy the base to `sources/tailored/Resume_<Company>.tex`, then edit only that working file with surgical `Edit` calls. `<Company>` is a short slug (for example, `Resume_AcmeCorp.tex`).

5. Compile. Change into `sources/tailored` and run `tectonic Resume_<Company>.tex`. On error, read the log and escape any unescaped `%`, `&`, `_`, `#`, or `$` in the text you added, then recompile. Confirm the output PDF path.

6. Report back:
   - Which JD keywords drove the changes.
   - Exactly which bullets were removed and added per block, so the user can sanity-check truthfulness.
   - Any JD requirement that was a real gap and was deliberately NOT added.
   - The output `.tex` and `.pdf` paths.

## First-run setup

- If `tectonic` is missing: `brew install tectonic`.
- If `sources/tailored` is missing: `mkdir -p sources/tailored`.

## Guardrails

- NEVER edit the base resume to tailor for a job. Only update the base if the user says their real, permanent resume has changed.
- When unsure whether a claim is truthful, ask rather than invent.
- Default to fewer edits: small, surgical, narrative-fitting changes, not a rewrite.
