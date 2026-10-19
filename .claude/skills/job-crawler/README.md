# Job Crawler

Crawls a company's careers page to find open positions, then ranks the top 3 roles you're most qualified for based on your resume and skill domains.

## What It Does

When you share a careers page URL (or just mention a company), this skill:

1. **Detects the ATS platform** (Lever, Greenhouse, Ashby, Recruitee, Workable) and hits its JSON API for reliable data
2. **Filters roles** by your location preferences and exclusion keywords
3. **Matches on transferable skills**, not just job titles — reads actual descriptions to find hidden gems
4. **Scores each role 0-100** using weighted factors: core skill overlap (35%), experience level (20%), domain relevance (20%), gap severity (15%), growth opportunity (10%)
5. **Presents the top 3** with match breakdowns, resume recommendations, and honest gap assessments

## Install

```bash
cp -r job-crawler/ ~/.claude/skills/
```

## Configuration

Uses `config.yaml` (one level up from the skill folder). Key fields:

- `resume.google_doc_id` — **required** — your resume Google Doc
- `resume.profile_summary` — **recommended** — 2-3 sentence summary for quick matching
- `skills.domains` — **recommended** — your transferable skill domains
- `preferences.level` — your target experience level
- `preferences.primary_specialty` — your primary platform/domain
- `preferences.us_only` — location filter
- `preferences.exclude_keywords` — terms that disqualify roles

On first run, the skill will guide you through setup if config isn't found.

## Usage

- *"What's open at Stripe?"*
- *"Crawl Palantir's careers page"*
- *"Anything good at https://jobs.lever.co/acme?"*
- *"Find roles at Figma for me"*

## Supported Platforms

| Platform | Detection |
|----------|-----------|
| Lever | `jobs.lever.co/*` |
| Greenhouse | `boards.greenhouse.io/*` |
| Ashby | `jobs.ashbyhq.com/*` |
| Recruitee | `*.recruitee.com` |
| Workable | `apply.workable.com/*` |
| Other | Falls back to browser-based scraping |
