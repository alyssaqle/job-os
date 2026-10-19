# Job Form Filler

Automatically fills out job application forms on career sites using your profile data and resume. Fills every field but **never clicks submit** — you always review and submit manually.

## What It Does

When you share a job application URL, this skill:

1. **Navigates to the application form** — handles Lever, Greenhouse, Ashby, Workday, and custom career sites
2. **Reads the job description** for context to tailor open-ended answers
3. **Maps all form fields** — text inputs, dropdowns, radio buttons, file uploads, textareas
4. **Fills everything** using your profile data: personal info, links, work authorization, EEO demographics, and experience-based answers
5. **Writes tailored open-ended answers** that reference your real experience and connect it to the specific role
6. **Reviews and reports** — screenshots the filled form and highlights anything you should double-check

## Install

```bash
cp -r job-form-filler/ ~/.claude/skills/
```

## Configuration

Uses `config.yaml` (one level up from the skill folder). Key fields:

- `user.*` — **required** — name, email, phone, location, links
- `preferences.authorized_to_work` / `requires_sponsorship` — for yes/no questions
- `eeo.*` — optional — voluntary demographic preferences (or "decline" to skip)
- `resume.google_doc_id` — for pulling experience details

On first run, the skill will guide you through setup if config isn't found.

## Usage

- *"Fill this out for me: https://jobs.lever.co/acme/apply"*
- *"Apply to this role"*
- *"Fill the form at [URL]"*
- *"Autofill this application"*

## Safety

The skill has a hard rule: **it will never click Submit, Send, or Apply buttons.** You always get the final review and submit yourself. It will also never fabricate experience — open-ended answers are grounded in your actual resume.

## Supported Platforms

Works best with Lever, Greenhouse, Ashby, and Workday. Falls back to generic form-filling for other platforms.
