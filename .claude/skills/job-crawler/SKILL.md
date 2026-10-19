---
name: job-crawler
description: >
  **Job Posting Crawler & Matcher**: Crawls a company's career page to find open positions, then ranks the top 3 roles the user is most qualified for based on their resumes. Use this skill whenever the user shares a company careers URL and wants to find the best-fit roles, or mentions "crawl jobs", "scan careers page", "find roles at [company]", "what positions are open", "best fit roles", or "top jobs for me". Also trigger when the user pastes a careers/jobs URL and asks which roles to apply for, or says something like "check out what [company] has open" or "anything good at [company]?". Trigger even for casual mentions like "palantir careers" or "jobs at stripe".
---

# Job Posting Crawler & Matcher

You help the user find the best-fit engineering roles at a specific company by crawling their career page, filtering for relevant positions, and ranking the top 3 based on their resume and experience.

## First-Run Setup

Before starting the workflow, check if `config.yaml` exists in the parent directory (one level up from this skill folder). Read the `user`, `resume`, `skills`, and `preferences` sections.

**If config.yaml does NOT exist or the `resume.google_doc_id` field is empty:**
1. Tell the user: "This is your first time using job-crawler. I need to set up your profile — this only happens once."
2. Ask for the required fields using AskUserQuestion:
   - Google Doc ID for their resume
   - A 2-3 sentence profile summary (title, years, key skills)
   - Their transferable skill domains (list 5-10)
   - Experience level and years
   - Primary specialty (e.g., "backend", "iOS", "fullstack")
   - Any hard filters (e.g., "US only", "no defense roles")
3. Write the responses to `config.yaml` in the parent directory
4. Confirm setup is complete, then proceed

**If config.yaml exists and has the required fields:**
Read it silently and proceed.

## Source Documents

Fetch the user's resume from Google Drive at the start of every run. Read the document ID from `config.yaml` → `resume.google_doc_id`.

Also read these fields from config to guide matching:
- `resume.profile_summary` — quick reference for the user's background
- `resume.variants` — which resume variants exist
- `skills.domains` — transferable skill domains for matching
- `preferences.level` — target experience level
- `preferences.years_experience` — years of experience
- `preferences.primary_specialty` — primary platform/domain
- `preferences.secondary_specialties` — acceptable secondary matches
- `preferences.us_only` — location filter
- `preferences.exclude_keywords` — keywords that disqualify roles

## Hard Filters

Apply these before any ranking. Read them from `config.yaml` → `preferences`:

1. **Location filter.** If `us_only` is true, exclude roles exclusively based outside the US. If a role has both US and non-US locations, include it but only note the US locations. Remote roles are fine as long as they're eligible for the user's location.

2. **Keyword exclusions.** Check each role against `preferences.exclude_keywords`. Exclude roles whose title or description contains these terms as hard requirements. If a term appears as "nice to have" or "preferred," include the role but flag it clearly.

## Workflow

### Step 1: Identify the ATS Platform

The user provides a careers page URL. Detect which Applicant Tracking System (ATS) the company uses, because each has a public JSON API that's far more reliable than scraping HTML.

**Known platforms and their API patterns:**

| Platform | Career page URL pattern | API endpoint |
|----------|------------------------|--------------|
| **Lever** | `jobs.lever.co/{company}` or company site embedding Lever | `https://api.lever.co/v0/postings/{company}?mode=json` |
| **Greenhouse** | `boards.greenhouse.io/{company}` or company site embedding Greenhouse | `https://api.greenhouse.io/v1/boards/{company}/jobs?content=true` |
| **Ashby** | `jobs.ashbyhq.com/{company}` | `https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true` |
| **Recruitee** | `{company}.recruitee.com` | `https://{company}.recruitee.com/api/offers` |
| **Workable** | `apply.workable.com/{company}` | `https://apply.workable.com/api/v1/widget/accounts/{company}` |

**How to detect the platform:**
1. Look at the URL the user provided. If it matches a known pattern above, use that API directly.
2. If it's the company's own domain (e.g., `acme.com/careers`), fetch the page using browser tools or WebFetch and look for clues in the HTML: embedded iframes pointing to lever.co, greenhouse.io, ashbyhq.com, etc., or script tags / API calls to these domains.
3. Extract the `{company}` slug from the detected platform URL.

**If the platform is unknown or detection fails**, fall back to using browser tools (read_page, get_page_text) to read the careers page directly and extract job listings from the rendered content.

### Step 2: Fetch and Filter Job Listings

Once you've identified the platform, hit the appropriate API endpoint using WebFetch.

**Important: Narrow early, but not too narrowly.** The goal is to focus on relevant roles without missing good transferable-skill matches.

1. **Filter by category/team first.** Most APIs return a `team`, `department`, or `categories` field. Look for values related to the user's domain — Engineering, Software, Technology, Product Development, Platform, Infrastructure, etc.

2. **Apply hard filters.** Remove roles that fail the location or keyword exclusion filters from config.

3. **Cast a wide net on titles, then narrow by reading descriptions.** This is the most important step. Don't just match on obvious title keywords — many of the best-fit roles have titles that don't obviously match. Instead, use the user's `skills.domains` and `preferences.primary_specialty` to guide a tiered approach:

   **Tier 1 — Direct matches (always include):**
   Roles whose titles directly match the user's primary specialty. These should almost always rank highest.

   **Tier 2 — Transferable-skill matches (include and read descriptions):**
   Roles in adjacent areas covered by the user's skill domains. Read the actual job description to determine fit — titles are misleading.

   **Tier 3 — Only if nothing better exists:**
   Roles further from core strengths. Include these only when Tiers 1-2 are sparse.

   The key insight: a role title might not match the user's specialty, but the actual work might align perfectly with their skill domains. **Read the actual job description** for Tier 2 roles before deciding to include or exclude them.

4. **Deduplicate similar roles.** Many companies post the same role at multiple levels or locations. **Treat the same role in different locations as ONE entry.** List it once and note all available locations. Same applies to different levels — pick the level closest to the user's from config. Your top 3 must be 3 *distinct* roles.

After filtering, you should be working with a manageable set (ideally 8-15 roles).

### Step 3: Extract Job Details

For each candidate role from Step 2, extract enough detail to assess fit:

- **Lever**: `descriptionPlain`, `lists` (contains requirements, responsibilities, etc.)
- **Greenhouse**: `content` field (HTML — extract text), plus `location`, `metadata`
- **Ashby**: `descriptionHtml` or `descriptionPlain`, `compensationTierSummary`

If the API gives you full descriptions, use them directly. If it only gives titles and links, fetch the top 5-8 most promising individual posting pages.

From each description, extract:
- Title and level
- Location / remote policy
- Key responsibilities (summarized)
- Must-have requirements
- Nice-to-have requirements
- Tech stack mentioned
- Compensation (if available)
- Any flagged keyword mentions (from `preferences.exclude_keywords`)

### Step 4: Rank and Select Top 3

Compare each role against the user's resume. For each candidate role, compute a **Match Score (0-100)** based on these weighted factors:

| Factor | Weight | What to assess |
|--------|--------|----------------|
| **Core skill overlap** | 35% | How many of the role's required skills does the user have? Count direct matches and transferable matches from `skills.domains`. Score: % of requirements met. |
| **Experience level fit** | 20% | Compare the role's level to the user's from config. Exact match → 100%. One level above → 60%. One level below → 50%. Two+ levels off → 20%. |
| **Domain relevance** | 20% | How closely does the role's domain match the user's experience? Same domain → 100%. Adjacent domain → 70%. Unrelated → 30%. |
| **Requirement gap severity** | 15% | 0 must-have gaps → 100%. 1 minor gap → 80%. 1 major gap → 50%. 2+ major gaps → 20%. A "major gap" is a core technology the role centers on that the user has no experience with. |
| **Growth opportunity** | 10% | Does the role expand the user's skill set while leveraging strengths? New domain + familiar skills → 100%. Same domain + same skills → 50%. Entirely new everything → 30%. |

**Present the match score for each role** so the user can quickly gauge fit. Be honest — a 45/100 match is useful information. It means "this is the best available but it's a stretch."

Select the top 3 by match score. If there aren't 3 strong matches, include the closest available and be transparent about the gaps.

### Step 5: Present Results

Output a ranked list in the chat. For each of the top 3 roles:

**[Rank]. [Job Title] — [Location / Remote] — Match: [X/100]**
- **Link:** [posting URL]
- **Match breakdown:** One line per factor showing the sub-score and why.
- **Why it fits:** 2-3 sentences connecting the role requirements to specific things from the user's resume. Reference concrete achievements where possible.
- **Key gaps:** Anything the role asks for that the user doesn't have. Be specific and honest.
- **Which resume:** Recommend which resume variant to use (from `resume.variants`) and why.
- **Compensation:** Include if available from the listing.
- **Flagged concerns:** Any keyword matches from exclusion filters that appeared as "preferred" rather than required.

After the top 3, include a brief **"Also considered"** section listing other roles that were close but didn't make the cut, with one-line reasons and their match scores.

If no roles are a good fit, say so clearly. "There's nothing great here right now — the best I found is X at 35/100" is a valid and useful output.

## Important Notes

- **Match on transferable skills, not just title keywords.** Always read job descriptions before judging fit — titles are misleading.
- **Speed over perfection.** The user wants a quick scan, not a dissertation. Keep the output tight and scannable.
- **Narrow early, go deep on finalists.** Don't fetch and analyze 50 job descriptions. Filter first, then only do full analysis for the top ~5.
- **Honesty matters.** If the user is not a fit for any roles at this company, say so.
- **Deduplicate aggressively.** Same role at different locations = one entry.
- **Level matters.** Use the user's level from config to flag roles that are a stretch up or potentially underleveled.
- **Primary specialty first.** If `preferences.primary_specialty` is set and a company has roles matching both primary and secondary specialties, the primary should always rank higher.
