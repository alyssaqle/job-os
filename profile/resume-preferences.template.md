# Resume Preferences

> Copy this file to `resume-preferences.md` and adjust to taste. Your `resume-preferences.md` is gitignored.

Format rules the assistant follows when tailoring or generating your resume.

## Layout

- **One page.** Trim older or weaker items first.
- **ATS-friendly:** single column, standard section headings (Experience, Education, Skills), no tables, no text boxes, no images, no icons that carry meaning.
- **Most recent and strongest first** in every section.
- Standard fonts; readable size; consistent date format (e.g. `Jan 2022 - Present`).

## Content

- Lead each bullet with a strong verb and **quantify impact** wherever you honestly can (latency, throughput, cost, time saved, users, revenue).
- Keep every claim consistent with `experience.md`. Never invent metrics.
- Cut filler adjectives. Show the result, not the effort.
- Tailor wording to the job description's language without copying it verbatim or claiming skills you lack.

## Technical skills

Group skills so a reader scans them fast:

- **Languages:** Python, Go, SQL
- **Frameworks:** (yours)
- **Infra / Cloud:** AWS, Docker, Kubernetes
- **Data:** (yours)

## Style

- **No em dashes anywhere.** Use commas, "and", or restructure the sentence. Em dashes read as AI-generated and hurt credibility.
- Consistent punctuation (pick: periods on all bullets or none).
- US or your locale spelling, applied consistently.

## LaTeX cleanup notes (if using a LaTeX source)

- Escape special characters: `%`, `&`, `#`, `_`, `$`.
- Keep one master `.tex`; make surgical per-job edits rather than rewriting.
- Compile to PDF and verify it stays one page before exporting.
- Check that links (LinkedIn, GitHub, portfolio) resolve and render.
