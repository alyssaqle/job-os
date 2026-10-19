# Job Analyzer

Analyzes job descriptions against your resumes and achievement history to provide tailored resume suggestions, a brief intro email, company research, and an honest compatibility assessment.

## What It Does

When you share a job posting URL, this skill:

1. **Picks the best resume variant** for the role and explains why
2. **Suggests 2-5 surgical resume changes** — bullet swaps, reordering, skill additions — grounded in your actual achievements (never fabricated)
3. **Drafts an intro email** (~80-100 words) that shows real understanding of the company, not generic templates
4. **Compiles a company quick-reference** — what they do, funding, leadership, culture signals
5. **Gives a compatibility assessment** with clear ✅/⚠️/❌ indicators for each requirement

## Install

```bash
cp -r job-analyzer/ ~/.claude/skills/
```

## Configuration

Uses `config.yaml` (one level up from the skill folder). Key fields:

- `resume.google_doc_id` — **required** — your resume Google Doc
- `resume.variants` — names of your resume variants
- `achievements.google_doc_id` — optional but recommended — a detailed brag doc for richer suggestions

On first run, the skill will guide you through setup if config isn't found.

## Usage

- *"What do you think of this role? https://..."*
- *"Analyze this JD for me"*
- *"How's my fit for this position?"*
- *"Check out this job at Stripe"*

## Output

Results appear in the chat in a scannable format. Also generates a `.docx` document with all sections saved to your workspace.
