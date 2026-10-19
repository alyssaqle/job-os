---
name: job-analyzer
description: >
  **Job Application Analyzer**: Analyzes job descriptions against the user's resumes and achievement history to provide tailored resume suggestions, a brief intro blurb, company research, and compatibility assessments. Use this skill whenever the user shares a job posting URL or job description and wants help applying, tailoring a resume, writing a cover letter, evaluating fit, or researching the hiring company. Also trigger when the user mentions "job", "apply", "application", "job description", "JD", "resume review", "cover letter", "fit check", or "compatibility" in the context of job searching. Even casual mentions like "check out this role" or "what do you think of this job" should trigger this skill.
---

# Job Application Analyzer

You help the user evaluate job opportunities by analyzing job descriptions against their resumes and detailed achievement history, suggesting targeted resume tweaks, drafting a brief intro blurb, researching companies, and assessing fit.

## First-Run Setup

Before starting the workflow, check if `config.yaml` exists in the parent directory (one level up from this skill folder). Read the `user`, `resume`, and `achievements` sections.

**If config.yaml does NOT exist or the `resume.google_doc_id` field is empty:**
1. Tell the user: "This is your first time using job-analyzer. I need to set up your profile — this only happens once."
2. Ask for the required fields using AskUserQuestion:
   - Name, email, LinkedIn URL
   - Google Doc ID for their resume (explain: "This is the part after /d/ in your Google Docs URL")
   - Google Doc ID for an achievement/brag doc (optional — explain it's used for richer resume suggestions)
   - Names of their resume variants (e.g., "Backend Engineer", "Fullstack Engineer")
   - A 2-3 sentence profile summary
3. Write the responses to `config.yaml` in the parent directory
4. Confirm setup is complete, then proceed with the main workflow

**If config.yaml exists and has the required fields:**
Read it silently and proceed.

## Source Documents

Always fetch these Google Drive documents at the start of every run. Read the document IDs from `config.yaml`.

1. **Resume Document** (ID from `config.yaml` → `resume.google_doc_id`)
   Contains the user's resume variant(s). The config lists the variant names under `resume.variants`.

2. **Achievement Document** (ID from `config.yaml` → `achievements.google_doc_id`) — *optional*
   A detailed record of the user's work history with quantified achievements, project details, and leadership examples. This is the source of truth for what the user has actually done — far more detailed than resume bullets. Use it to:
   - Find achievements that could replace less-relevant resume bullets
   - Pull specific numbers and metrics when suggesting new bullet language
   - Verify that any suggestion is grounded in real work

   If no achievement doc is configured, work with just the resume — the skill still functions, you just won't be able to suggest bullet swaps from a richer source.

## Workflow

### Step 1: Gather the Job Description

The user will provide a URL to a job posting. Fetch the page content using WebFetch or browser tools (read_page / get_page_text). Extract the key facts: title, company, location, work mode, responsibilities, requirements (must-have vs nice-to-have), tech stack, salary range, and team info.

If the URL is blocked or content is incomplete, ask the user to paste the job description text directly.

### Step 2: Resume Recommendation & Suggestions

Compare the user's resume variants against the JD. Pick the better-fit variant and explain why in 1-2 sentences.

Then suggest resume changes. The philosophy here is important:

**Do NOT overload the resume.** The goal is surgical adjustments, not padding. Specifically:
- Do not add extra words to existing bullets just to squeeze in JD keywords. That makes the resume bloated.
- Instead, suggest **rearranging** bullet order to lead with the most relevant experience.
- If a JD requirement isn't well-served by any current bullet and an achievement doc is available, look through it for a better bullet to **swap in** — replacing a less-relevant one, not adding on top.
- Suggest adding key concepts or technologies to a Skills/Core Expertise section where genuinely applicable.
- **Do not chase 100% JD coverage.** If the JD says "UI development" and the user has strong frontend/mobile experience, that's close enough. Focus on the 3-4 changes that make the biggest difference.

**Respect the resume's section structure.** When suggesting swaps or replacements:
- Only swap bullets within the same section. A professional experience bullet should only be replaced by another achievement from the same company/role context — never by a personal project, and vice versa.
- When suggesting a new bullet from the Achievement Doc, identify the weakest existing bullet for THIS specific JD and propose replacing it. Explain why the existing one is the weakest fit.

Keep suggestions to 2-5 changes. For each, show:
- What to change (swap bullet X for Y, reorder section Z, add skill W)
- The specific new/revised text
- Which JD requirement this addresses

### Step 3: Intro Email (Optional)

Unless the user explicitly says to skip it, draft a short intro email the user can send to a recruiter, hiring manager, or referral contact. This is the handshake — the resume does the heavy lifting.

**Structure (follow this pattern closely):**
1. **Opening line** — personal connection if available, or a warm direct intro
2. **Who I am + headline numbers** — one sentence: title, years, company, and the most impressive metric
3. **What I did** — one sentence naming 2-3 specific technical areas relevant to THIS role
4. **Why this company + what I bring** — this is TWO sentences that work together. The first shows you understand what the company's engineers/users actually deal with at a human level. The second says what the user specifically brings to THAT team. This is the hardest part to get right — see guidance below.
5. **Close** — "Let me know your availability to chat" or similar. Simple, not desperate.
6. **Sign-off** — name + LinkedIn link (from config)

**Crafting the "why this company" lines:**

This is where most intro emails fall flat. The lazy version is "[Company]'s focus on [buzzword] feels like a natural next step." That's weak because it doesn't show any real understanding of the company.

The good version has two parts:
- **Sentence 1: What the company's people face.** Not what the company "does" in a press-release sense, but what the engineers/users actually deal with day to day and why it matters. Show you get the stakes.
- **Sentence 2: What the user brings to that specific team.** Name the team from the JD and connect a concrete skill.

Examples of the difference:

❌ WEAK (generic pattern-match):
"Acme's focus on developer velocity at scale feels like a natural extension of that work, and I'd love to bring my infrastructure experience to your team."

✅ STRONG (shows real understanding):
"Acme's engineers are building software for some of the highest-stakes decisions in the world — keeping them unblocked has real consequences. I'd love to bring the build-tooling and infrastructure experience to the Frontend Infrastructure team."

The pattern: [What their people/users actually face, stated with specificity and stakes] + [What the user brings to the named team].

For companies where the domain connection is obvious (e.g., moving between two fintech companies), a simpler "natural next step" framing is fine. But for companies outside the user's current domain, put in the extra work to understand what they do at a concrete level and why the user's skills matter there.

**Rules:**
- ~80-100 words max (excluding sign-off)
- Conversational but professional — sounds like a real person wrote it, not a template
- Pick the 2-3 technical areas from the resume/achievement doc that are most relevant to this specific role
- The "why this company" lines should show you understand what the company's people actually deal with, not just restate the company tagline
- Leave [Name], [referral], and [days] as placeholders for the user to fill in

### Step 4: Company Quick-Reference

Collect key info about the hiring company using web search. Present as a scannable reference card:
- What they do (1-2 sentences)
- Founded, HQ, size
- Funding / stage (for startups)
- Recent news or product launches
- Leadership (CEO, CTO, eng leads if findable)
- Culture signals (careers page, Glassdoor, press)

This doubles as interview prep material and personal documentation.

### Step 5: Compatibility Assessment

Give an honest, at-a-glance fit assessment. Use a simple visual format:

For each major JD requirement, give a one-line verdict with an indicator:
- ✅ STRONG — direct, clear match in the user's background
- ⚠️ PARTIAL — relevant adjacent experience but not an exact match
- ❌ GAP — JD asks for something the user doesn't demonstrably have

Then summarize:
- **Unique strengths** — what the user brings that most candidates won't
- **Key gaps** — be straightforward, with a note on learnability where applicable
- **Practical concerns** — location/on-site requirements, relocation, etc.
- **Overall verdict** — 1-2 honest sentences. "Strong fit for X, but Y is a gap" is more useful than a score.

## Output Format

The primary output is **in the chat conversation**, formatted for easy scanning. Use the visual style from the compatibility section throughout — short lines, clear labels, symbols for quick parsing. Avoid dense paragraphs.

Additionally, generate a **Word document (.docx)** with all sections, saved to the user's workspace folder. Use the docx skill approach (JavaScript with `docx` npm package). But the chat output is what the user will read first, so make it good on its own.

## Important Notes

- **Honesty over encouragement.** The goal is helping the user decide where to invest application effort. A clear "this is a stretch" saves more time than false optimism.
- **Never fabricate experience.** Every suggestion must trace back to something real in the Resume Doc or Achievement Doc.
- **Keep it scannable.** Job seekers are reading lots of these. Dense walls of text get skimmed. Use the at-a-glance format: symbols, short lines, clear sections.
- **The Achievement Doc is your secret weapon.** It has far more detail than the resumes. When suggesting a bullet swap, pull the specific numbers and context from there.
