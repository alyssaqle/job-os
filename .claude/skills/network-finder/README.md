# Network Finder

Searches your LinkedIn connections and an optional referral spreadsheet to find warm intro paths at a target company.

## What It Does

When you mention a company, this skill:

1. **Searches your referral spreadsheet** (if configured) — finds contacts who are explicitly offering referrals at that company
2. **Searches LinkedIn** for 1st-degree connections at the company using the connection filter
3. **Presents a quick-reference card** showing what it found and suggesting next steps

## Install

```bash
cp -r network-finder/ ~/.claude/skills/
```

## Configuration

Uses `config.yaml` (one level up from the skill folder). Key fields:

- `network.linkedin_profile_url` — **required** — your LinkedIn profile URL
- `network.referral_sheet_url` — optional — URL to a Google Sheet tracking referral contacts
- `network.referral_sheet_structure` — describe the columns if you have a referral sheet

On first run, the skill will guide you through setup if config isn't found.

### Referral Spreadsheet

If you or your network maintains a spreadsheet of people offering referrals (common among alumni groups, company Slack channels, etc.), point this skill at it. The skill will search it before LinkedIn for higher-signal results.

## Usage

- *"Do I know anyone at Airbnb?"*
- *"Find me a referral at Stripe"*
- *"Who do I know at Google?"*
- *"Check my network for Figma connections"*

## Requirements

- **LinkedIn login** — you must be logged into LinkedIn in the browser for connection searches to work
- **Google Sheets access** — if using a referral spreadsheet hosted on Google Sheets
