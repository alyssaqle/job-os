---
name: job-apply
description: Fill out job applications automatically using your resume. Use when the user wants to apply for jobs on LinkedIn Easy Apply, Greenhouse, Ashby, or Workday.
allowed-tools: Read, Write, Bash, mcp__claude-in-chrome__*, mcp__plugin_playwright_playwright__*
---

# Job Application Assistant

A Claude Code skill for filling job applications on LinkedIn Easy Apply, Greenhouse, Ashby, Lever, Rippling, and Workday using browser automation.

## Initial Prompt

When this skill is invoked, first check if a profile exists at `~/.claude-job-profile.json`.

**If NO profile exists**, say:

> Welcome to the Job Application Assistant! I'll help you fill out job applications on LinkedIn, Greenhouse, and Workday.
>
> First, I need to set up your profile. This is a one-time process — your information will be saved for future applications.
>
> **Please provide the path to your resume file** (PDF, DOCX, or TXT).
>
> For example: `~/Documents/resume.pdf` or `/Users/you/Desktop/MyResume.pdf`

Then wait for the user to provide the path before proceeding with profile extraction.

**If a profile DOES exist**, say:

> Welcome back! Your profile is loaded from `~/.claude-job-profile.json`.
>
> **Provide a job URL** and I'll help you apply. For example:
> - LinkedIn: `https://www.linkedin.com/jobs/view/123456789`
> - Greenhouse: `https://boards.greenhouse.io/company/jobs/123`
> - Workday: `https://company.wd5.myworkdayjobs.com/jobs/job/123`
>
> Or say **"reset profile"** if you want to update your information from a new resume.

---

## Required Input

- **Resume file path**: Path to your resume (PDF, DOCX, or TXT format)
- **Job URL**: LinkedIn job posting or direct application link

## Profile Storage

Your extracted profile is stored at `~/.claude-job-profile.json` for reuse across sessions. Run with `--reset-profile` to re-extract from resume.

---

## Dual-Tool Architecture

This skill uses **two browser automation tools** together because each has capabilities the other lacks:

| Capability | Chrome MCP | Playwright MCP |
|---|---|---|
| Authenticated sessions (LinkedIn) | Yes | No — runs a separate browser with no login |
| File uploads | No — opens OS file picker that can't be controlled | Yes — `setInputFiles` and `browser_file_upload` |
| Iframe interaction | Limited — can't reliably reach iframe content | Yes — snapshots include iframe elements transparently |
| JavaScript injection | Yes — `javascript_tool` | Yes — `browser_evaluate` and `browser_run_code` |
| Dropdown/combobox interaction | Limited | Yes — `browser_fill_form` and `browser_click` |

### Tool Routing Rules

**Use Chrome MCP (`mcp__claude-in-chrome__*`) for:**
- LinkedIn navigation (requires logged-in session)
- Any site requiring authentication
- JavaScript injection to capture external URLs
- Reading LinkedIn job details

**Use Playwright MCP (`mcp__plugin_playwright_playwright__*`) for:**
- External application portals (Greenhouse, Ashby, Lever, Rippling, Workday)
- File uploads (resume, cover letter)
- Forms embedded in iframes
- Dropdown and combobox interaction
- Any form filling on non-authenticated pages

### The Handoff Pattern

1. **Chrome MCP** navigates to the LinkedIn job listing (authenticated)
2. **Chrome MCP** clicks Apply — if it's an external application, captures the external URL via JavaScript interception
3. **Playwright MCP** opens the captured URL and fills the form, uploads files, and submits

---

## LinkedIn → External URL Extraction

When a LinkedIn job uses an external application portal, the Apply button opens a new tab. Use JavaScript interception to capture that URL.

### Pattern A: Button with `window.open` (most common)

```javascript
// Step 1: Set up interceptor in Chrome MCP
var originalOpen = window.open;
window.open = function(url, target, features) {
  document.title = 'CAPTURED:' + url;
  var w = originalOpen.call(window, url, target, features);
  return w;
};

// Step 2: Click the Apply button
document.querySelector('button.jobs-apply-button').click();

// Step 3: Read document.title — it will start with "CAPTURED:" followed by the URL
```

### Pattern B: Link with `target="_blank"` (fallback)

```javascript
// Remove target="_blank" so it navigates in the same tab
var link = document.querySelector('a.jobs-apply-button');
link.removeAttribute('target');
link.click();
// Read the URL from the Chrome tab after navigation
```

After capturing the URL, pass it to Playwright MCP via `browser_navigate`.

---

## Workflow

### Phase 1: Profile Setup

If no profile exists at `~/.claude-job-profile.json`, or if the user requests a reset:

1. **Read the resume file** using the Read tool
2. **Extract structured data** into these categories:
   - `firstName`, `lastName`
   - `email`, `phone`
   - `location` (city, state, country, zip)
   - `linkedInUrl`, `portfolioUrl`, `githubUrl` (if present)
   - `workHistory[]`: array of { company, title, startDate, endDate, current, description }
   - `education[]`: array of { school, degree, field, startDate, endDate, gpa }
   - `skills[]`: array of skill strings
   - `resumePath`: absolute path to the resume file on disk
3. **Present extracted data to user** for review and correction
4. **Save confirmed profile** to `~/.claude-job-profile.json`

### Phase 2: Application Filling

1. **Load profile** from `~/.claude-job-profile.json`
2. **Determine starting point**:
   - If URL is LinkedIn (`linkedin.com`) → use **Chrome MCP** to navigate (authenticated)
   - If URL is a direct external portal → skip to step 5 with **Playwright MCP**
3. **Chrome MCP**: Navigate to LinkedIn job listing, click Apply
4. **Chrome MCP**: If external portal, capture URL using JS interception pattern (see above)
5. **Playwright MCP**: Navigate to external URL with `browser_navigate`
6. **Playwright MCP**: Detect platform, read form structure with `browser_snapshot`
7. **Playwright MCP**: Fill fields with `browser_fill_form`, handle dropdowns with `browser_click`
8. **Playwright MCP**: Upload resume with `browser_file_upload` or `browser_run_code` using `setInputFiles`
9. **Playwright MCP**: Take snapshot to verify all fields are filled correctly
10. **Present summary** to user showing all filled values, wait for explicit confirmation
11. **Playwright MCP**: Click Submit

---

## Platform-Specific Guidance

### LinkedIn Easy Apply

**Characteristics:**
- Modal-based multi-step wizard
- Usually 2-5 steps: Contact Info → Resume → Additional Questions → Review
- Has progress indicator at top

**Approach:**
1. Click "Easy Apply" button to open modal
2. Use `read_page` on each step to identify fields
3. Common fields:
   - Phone number (often pre-filled from LinkedIn)
   - Resume upload (use `upload_image` tool with resume path)
   - Work authorization questions (dropdowns)
   - Custom screening questions (varies by employer)
4. Click "Next" to advance, "Review" on final step
5. Screenshot the review page before "Submit application"

**Field patterns to look for:**
- `input[name*="phone"]` - Phone number
- `input[type="file"]` - Resume upload
- `select`, `[role="listbox"]` - Dropdown questions
- `[role="radio"]`, `[role="checkbox"]` - Multiple choice

### Greenhouse

**Characteristics:**
- Single long-form page with sections
- Clear field labels
- Often has "Add another" for work history/education
- **Frequently embedded in iframes** on company career sites — Playwright handles this transparently

**Approach (use Playwright MCP):**
1. Navigate to URL with `browser_navigate`
2. Use `browser_snapshot` to read full form — iframe content appears with `f54eXX` refs
3. Fill from top to bottom using `browser_fill_form`
4. **Phone country code**: Click the country code toggle → select "United States: +1" from the listbox → the phone field auto-formats with +1 prefix
5. For work history sections:
   - Fill most recent position
   - Click "Add another" if form allows and user has more history
6. Education section similar pattern
7. Handle custom questions at bottom
8. Upload resume via `browser_file_upload` or `browser_run_code` with `setInputFiles`
9. Single "Submit Application" button at end

**Field patterns:**
- Standard `<input>` and `<select>` elements
- `#first_name`, `#last_name`, `#email`, `#phone` common IDs
- `.field-container` or `.field` wrapping each question

### Ashby

**Characteristics:**
- Simple single-page form
- Fields: name, phone, email, location (combobox), LinkedIn URL, resume upload
- Has both a resume upload field and a separate autofill file input — use the resume field, not the autofill one

**Approach (use Playwright MCP):**
1. Navigate to URL with `browser_navigate`
2. Use `browser_snapshot` to read form structure
3. Fill text fields with `browser_fill_form` (name, phone, email, LinkedIn URL)
4. **Location combobox**: Type the location to trigger suggestions, then click the matching option
5. **Resume upload**: Use `browser_run_code` with `page.locator('#_systemfield_resume').setInputFiles('/path/to/resume.pdf')` — target `#_systemfield_resume` specifically, not the autofill input
6. Verify with `browser_snapshot`
7. Submit

### Lever

**Characteristics:**
- Often hosted on the company's own domain (e.g., `company.com/careers/...?lever-source=LinkedIn`)
- Form typically at the bottom of a long job description page
- Text fields for name, email, phone, LinkedIn, etc.
- Radio buttons for screening questions — often use custom overlays that intercept clicks

**Approach (use Playwright MCP):**
1. Navigate to URL with `browser_navigate`
2. Scroll down to find the application form (usually below job description)
3. Use `browser_snapshot` to read form structure
4. Fill text fields with `browser_fill_form`
5. **Radio buttons**: If `browser_click` doesn't work (overlay intercepts), use `browser_evaluate` with:
   ```javascript
   element.click();
   element.dispatchEvent(new Event('change', {bubbles: true}));
   ```
6. **Resume upload**: Use `browser_run_code` to find the hidden file input and call `setInputFiles`:
   ```javascript
   async (page) => {
     await page.locator('input[type="file"][name="resume"]').setInputFiles('/path/to/resume.pdf');
   }
   ```
7. Verify with `browser_snapshot`, then submit

### Rippling

**Characteristics:**
- Auto-parses uploaded resume to pre-fill fields
- Upload resume first, then verify/correct auto-filled data
- Location uses a typeahead combobox

**Approach (use Playwright MCP):**
1. Navigate to URL with `browser_navigate`
2. **Upload resume first** — Rippling will auto-parse and fill fields
3. Use `browser_snapshot` to see what was auto-filled
4. Correct any mis-parsed fields with `browser_fill_form`
5. **Location combobox**: Clear existing value, type the correct location, wait for dropdown, click match
6. Fill any remaining required fields
7. Verify with `browser_snapshot`, then submit

### Workday

**Characteristics:**
- Multi-page wizard with heavy JavaScript
- Non-standard UI components (custom dropdowns, date pickers)
- Often requires account creation (STOP and inform user - do not create accounts)

**Approach (use Playwright MCP):**
1. If login/account creation required, STOP and inform user they must handle this
2. Navigate through "My Information" → "My Experience" → "Application Questions"
3. Use `browser_snapshot` to read form structure on each page
4. For dropdowns: `browser_click` to open, then `browser_snapshot` to read options, then `browser_click` option
5. For date fields: May need to click calendar icon, then select date
6. Watch for "Save and Continue" vs "Submit" buttons
7. Upload resume via `browser_file_upload` or `browser_run_code`

**Special handling:**
- Workday dropdowns: Click field → wait → read options with `browser_snapshot` → click option
- Date pickers: Often format-sensitive, try MM/DD/YYYY
- Required fields marked with asterisk or red border after validation

---

## Field Mapping Reference

| Profile Field | Common Form Labels |
|--------------|-------------------|
| firstName | First Name, Given Name, First |
| lastName | Last Name, Family Name, Surname, Last |
| email | Email, Email Address, E-mail |
| phone | Phone, Phone Number, Mobile, Cell |
| location.city | City |
| location.state | State, Province, State/Province |
| location.zip | Zip, Postal Code, ZIP Code |
| location.country | Country |
| linkedInUrl | LinkedIn, LinkedIn URL, LinkedIn Profile |
| workHistory[0].company | Current Company, Most Recent Employer, Company |
| workHistory[0].title | Current Title, Job Title, Position, Title |
| education[0].school | School, University, College, Institution |
| education[0].degree | Degree, Degree Type |
| education[0].field | Major, Field of Study, Concentration |

---

## Chrome MCP Tool Usage

### Reading Forms
```
Use read_page with filter: "interactive" to see all form fields
Use find with natural language: "email input field", "submit button"
```

### Filling Fields
```
Use form_input for standard inputs and selects:
  - ref: element reference from read_page
  - value: the value to set

Use computer with action: "left_click" for custom dropdowns:
  1. Click to open dropdown
  2. read_page to see options
  3. Click the correct option
```

### File Upload (Resume)
```
Use find to locate file input: "resume upload field"
Use form_input or computer to trigger file picker
Note: May need to use upload_image tool for some implementations
```

### Multi-Page Navigation
```
After filling current page:
1. find "next button" or "continue button"
2. Take screenshot for record
3. Click next
4. read_page on new step
5. Repeat until review/submit page
```

---

## Playwright MCP Tool Usage

### Reading Forms
```
Use browser_snapshot to get the full accessibility tree, including iframe content.
Iframe elements appear with refs like "f54eXX" — these refs work with all Playwright tools.
```

### Filling Fields
```
Use browser_fill_form with ref/value pairs from the snapshot:
  - fields: [{ name: "First Name", type: "textbox", ref: "ref123", value: "John" }]

For multiple fields at once, pass an array of field objects.
```

### Dropdowns and Comboboxes
```
1. browser_click on the dropdown toggle/button to open it
2. browser_snapshot to read the available options
3. browser_click on the correct option

For comboboxes (typeahead): type into the field first, then click the matching suggestion.
```

### File Upload
Two patterns depending on the form:

**Pattern A: Direct setInputFiles (preferred)**
```
Use browser_run_code:
  async (page) => {
    await page.locator('#resume-input').setInputFiles('/path/to/resume.pdf');
  }
Replace '#resume-input' with the actual selector for the file input.
```

**Pattern B: File chooser interception**
```
Use browser_run_code:
  async (page) => {
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.locator('button:has-text("Upload")').click()
    ]);
    await fileChooser.setFiles('/path/to/resume.pdf');
  }

If a modal appears after upload, use browser_file_upload to complete it.
```

### Iframe Interaction
```
Playwright handles iframes transparently.
browser_snapshot shows iframe content with refs (e.g., "f54eXX").
These refs work directly with browser_fill_form, browser_click, etc.
No special handling needed — just use the refs from the snapshot.
```

### Custom Radio Buttons
```
If browser_click is intercepted by overlays, use browser_evaluate:
  element.click();
  element.dispatchEvent(new Event('change', {bubbles: true}));
Pass the ref of the radio input element.
```

---

## Safety Rules

1. **Never enter passwords** - If login required, stop and instruct user
2. **Never create accounts** - Stop and inform user they must create accounts themselves
3. **Never click Submit without confirmation** - Always take a snapshot and get explicit "yes"
4. **Never enter payment information** - Some applications have optional premium features
5. **Handle sensitive questions carefully** - Salary expectations, visa status, disability disclosure should be confirmed with user before filling
6. **Always use Chrome MCP for LinkedIn** - Playwright cannot access authenticated sessions
7. **Never store or pass login credentials between tools** - Each tool uses its own browser context

---

## Example Invocation

```
User: Help me apply to this job: https://www.linkedin.com/jobs/view/123456789
