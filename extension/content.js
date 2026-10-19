// Runs on every page. Two jobs, both so I never have to log things by hand:
//  1. Notice "thanks for applying" pages -> mark the job applied.
//  2. On LinkedIn, notice when I click Send on a connection request or a message -> log the outreach.
// It only reports MY clicks on pages I'm already on. It never clicks, sends, or scrapes anything.
'use strict';

const APPLIED_RE = /(thank(s| you) for (applying|submitting|your application)|application (has been |was )?(submitted|received|sent)|we('ve| have) received your application|successfully (applied|submitted)|your application (is complete|is in|was sent))/i;

let reportedAppliedFor = '';
function checkApplied() {
  if (reportedAppliedFor === location.href) return;
  // Only headings, dialogs and alerts: a JD that *mentions* "once your application is received"
  // must not count. Confirmation pages put it in a heading (Greenhouse/Lever/Ashby) or a dialog
  // (LinkedIn Easy Apply, Workday).
  const spots = [...document.querySelectorAll('h1, h2, h3, [role="dialog"], [role="alert"], [role="status"], [aria-live]')]
    .map(el => el.innerText || '').join('\n').slice(0, 20000);
  const confirmUrl = /confirm|thank|success|submitted|applied/i.test(location.pathname + location.search);
  const text = confirmUrl ? (document.body?.innerText || '').slice(0, 5000) : spots;
  if (APPLIED_RE.test(text)) {
    reportedAppliedFor = location.href;
    chrome.runtime.sendMessage({ type: 'applied', url: location.href, title: document.title });
  }
}

let t;
const observer = new MutationObserver(() => { clearTimeout(t); t = setTimeout(checkApplied, 1500); });
if (document.body) observer.observe(document.body, { childList: true, subtree: true });
setTimeout(checkApplied, 1500);

// ---- LinkedIn outreach -----------------------------------------------------------------
if (location.hostname.endsWith('linkedin.com')) {
  document.addEventListener('click', e => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const label = (btn.getAttribute('aria-label') || btn.innerText || '').trim();
    if (!/^send\b/i.test(label)) return;

    // Connection request modal ("Send", "Send now", "Send without a note", "Send invitation")
    const dialog = btn.closest('[role="dialog"]');
    if (dialog && (/invit|without a note|send now/i.test(label) || dialog.querySelector('textarea[name="message"], #custom-message'))) {
      const note = dialog.querySelector('textarea')?.value || '';
      report('requested', note);
      return;
    }

    // Message / InMail composer
    const form = btn.closest('form, .msg-form, [class*="msg-form"]');
    if (form) {
      const body = form.querySelector('[contenteditable="true"], textarea')?.innerText
        || form.querySelector('textarea')?.value || '';
      const convo = form.closest('[class*="conversation"], [class*="convo"], main, aside') || document;
      report('messaged', body, convo);
    }
  }, true);
}

function profileUrl(scope) {
  if (/^\/in\//.test(location.pathname)) return location.origin + location.pathname;
  const a = (scope || document).querySelector('a[href*="/in/"]');
  return a ? a.href : '';
}

function report(kind, message, scope) {
  const url = profileUrl(scope);
  if (!url) return;
  chrome.runtime.sendMessage({ type: 'outreach', kind, linkedin_url: url, message });
}
