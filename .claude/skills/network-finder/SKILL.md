---
name: network-finder
description: >
  **Network & Referral Finder**: Searches the user's LinkedIn connections and a referral spreadsheet to find potential contacts at a target company. Use this skill whenever the user wants to find connections at a company, look for referrals, check if they know anyone at a company, or find a warm intro path. Trigger on mentions of "referral", "connection", "know anyone at", "warm intro", "network", "who do I know at", or any company name combined with intent to find contacts there.
---

# Network & Referral Finder

You help the user find warm intro paths to target companies by searching two sources: their LinkedIn connections and an optional referral/alumni spreadsheet.

## First-Run Setup

Before starting the workflow, check if `config.yaml` exists in the parent directory (one level up from this skill folder). Read the `user` and `network` sections.

**If config.yaml does NOT exist or the `network.linkedin_profile_url` field is empty:**
1. Tell the user: "This is your first time using network-finder. I need to set up your profile — this only happens once."
2. Ask for the required fields using AskUserQuestion:
   - Their LinkedIn profile URL (required — this is the core data source)
   - Whether they have a referral/alumni spreadsheet (Google Sheet or other). If yes:
     - The spreadsheet URL
     - The column structure (e.g., "Column A = Name, Column B = Company, Column C = Notes")
3. Write the responses to `config.yaml` in the parent directory
4. Confirm setup is complete, then proceed

**If config.yaml exists and has the required fields:**
Read it silently and proceed.

## Data Sources

### 1. Referral Spreadsheet (Optional)

Read the URL from `config.yaml` → `network.referral_sheet_url`. If this field is blank, skip this source entirely.

The spreadsheet contains contacts who have offered referrals at their companies. Read the column structure from `config.yaml` → `network.referral_sheet_structure`.

**Accessing the sheet:**
Use browser tools to open the spreadsheet, then search for the target company. The most reliable approach:
1. Navigate to the spreadsheet URL
2. Open Find and Replace via **Edit menu > Find and replace** (do NOT use Ctrl+F — it can get intercepted by cell edit mode in Google Sheets)
3. Type the company name in the Find field and click "Find"
4. If the dialog says "no entries matching," the company isn't in the sheet
5. If found, close the dialog and read the matching row for referrer contact info and details

**Caching:** If a local CSV copy exists at the workspace path and is less than 7 days old, search that first. Otherwise, access the live sheet via browser. To create a cache, export via `File > Download > CSV` in the browser.

### 2. LinkedIn Connections

Search the user's LinkedIn network for people currently at the target company.

- **Profile:** Read from `config.yaml` → `network.linkedin_profile_url`
- **Requires:** The user must be logged into LinkedIn in the browser

**Searching LinkedIn connections:**
1. Navigate to: `https://www.linkedin.com/search/results/people/?keywords=COMPANY_NAME&network=%5B%22F%22%5D`
   - The `network=["F"]` filter restricts results to 1st-degree connections only
2. Read the search results to find connections at the target company
3. For each match, note: name, current title, and LinkedIn profile URL
4. If no results with the exact company name, try common variations (e.g., "Block" vs "Block, Inc." vs "Square")

**Important:** LinkedIn may show a login wall or rate-limit searches. If the page doesn't load properly, let the user know they may need to log in or try again later. Don't repeatedly retry — one attempt is enough.

## Workflow

### Step 1: Identify the Target Company

The user will mention a company name (e.g., "Do I know anyone at Airbnb?" or "Find me a referral at Stripe"). Extract the company name and any common aliases (e.g., "Google" / "Alphabet", "Meta" / "Facebook").

### Step 2: Search Referral Spreadsheet

If a referral sheet is configured, search it first — these are the highest-value contacts because they're explicitly offering referrals.

Open the sheet in the browser, use Find to search for the company name. If found, read:
- Who the referrer is
- Their contact info
- Any special instructions or notes
- How recently the entry was updated

If the company isn't found, note that clearly — "No referral found for [company] in your spreadsheet."

If no referral sheet is configured, skip this step and note: "No referral spreadsheet configured — searching LinkedIn only."

### Step 3: Search LinkedIn Connections

Navigate to the LinkedIn people search with the 1st-connection filter. Read the results:
- Names and current titles of connections at the target company
- How many 1st-degree connections are there

If there are results, present the top matches (up to 5). If no results, try one alternate name for the company before reporting no matches.

### Step 4: Present Results

Format the output as a quick-reference card in the chat:

**[Company Name] — Network Check**

**Referral Spreadsheet:**
- [Found/Not found/Not configured]
- If found: Referrer name, contact info, any special instructions, date posted

**LinkedIn 1st Connections:**
- [N] connections found
- List each: Name — Title
- Or: No 1st-degree connections found

**Suggested Next Step:**
- If referral found: "Reach out to [name] via [channel] — they're actively offering referrals"
- If LinkedIn connection only: "You're connected to [name] — consider reaching out for an intro"
- If neither: "No warm path found. Consider a cold application or searching for 2nd-degree connections"

## Important Notes

- **Privacy:** Don't screenshot or save LinkedIn profile data beyond names and titles. This is just for the user's personal reference.
- **Referral sheet etiquette:** If the spreadsheet has notes about referral conditions (e.g., can't refer if you already applied independently), include this context when relevant.
- **Speed over completeness:** A quick answer ("yes, you have a referral path" or "no warm connections") is more valuable than an exhaustive search.
- **Freshness matters:** If a referral sheet entry is months old, flag that the referrer may have moved on. Suggest verifying before reaching out.
