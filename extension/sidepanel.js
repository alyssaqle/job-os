// The side panel follows whatever tab I'm on and shows the ONE relevant thing:
//   job page I'm tracking -> 1 Tailor  2 Apply  3 Reach out (with where I am highlighted)
//   job page I'm not      -> "Save this job" (+ tailor in the same click)
//   LinkedIn profile      -> who they are, which of my jobs they help with, a message in my voice
//   anything else         -> my Next Up
'use strict';

const API = 'http://localhost:8000';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const app = $('#app');

async function api(path, body, method) {
  const res = await fetch(API + path, {
    method: method || (body ? 'POST' : 'GET'),
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function banner(text, ms = 6000) {
  const b = $('#banner');
  b.textContent = text;
  b.classList.remove('hidden');
  clearTimeout(banner.t);
  banner.t = setTimeout(() => b.classList.add('hidden'), ms);
}

async function busy(btn, label, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  try { return await fn(); } catch (e) { banner('⚠️ ' + e.message, 8000); throw e; } finally { btn.disabled = false; btn.textContent = old; }
}

async function copy(text) { await navigator.clipboard.writeText(text); banner('Copied ✓', 1500); }

let meta = null;
let current = { tabId: null, url: '' };
const personCache = new Map(); // profile url -> page/person result (avoid re-reading on every tab switch)

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function pageText(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({ text: document.body.innerText.slice(0, 40000), title: document.title }),
    });
    return result;
  } catch { return { text: '', title: '' }; }
}

const looksLikeJob = t => /(responsibilit|qualification|requirement|what you'll do|about the role|you will|apply)/i.test(t)
  && /(experience|skills|degree|years)/i.test(t);

// ---------- router ----------
async function refresh(force) {
  const tab = await activeTab();
  if (!tab?.url?.startsWith('http')) return renderHome();
  if (!force && tab.url === current.url && tab.id === current.tabId) return;
  current = { tabId: tab.id, url: tab.url };
  try { meta = meta || await api('/api/meta'); } catch { return renderOffline(); }

  const u = new URL(tab.url);
  if (u.hostname.endsWith('linkedin.com') && u.pathname.startsWith('/in/')) return renderPerson(tab);
  const { job } = await api('/api/page/job', { url: tab.url }).catch(() => ({ job: null }));
  if (job) {
    chrome.runtime.sendMessage({ type: 'remember-job', tabId: tab.id, jobId: job.id });
    return renderJob(job.id);
  }
  const page = await pageText(tab.id);
  if (looksLikeJob(page.text)) return renderUntrackedJob(tab, page);
  return renderHome();
}

function renderOffline() {
  app.innerHTML = `<h1>Job OS isn't running</h1><p class="muted">In Terminal, from the job-2027 folder:</p>
    <div class="note">./run.sh</div><button class="btn block" id="retry">Try again</button>`;
  $('#retry').onclick = () => { meta = null; refresh(true); };
}

// ---------- home: next up ----------
async function renderHome() {
  let q = [];
  try { q = await api('/api/nextup'); } catch { return renderOffline(); }
  const top = q[0];
  app.innerHTML = `
    <div class="step current">
      <div class="small muted" style="font-weight:700;letter-spacing:.06em">NEXT UP</div>
      ${top ? `<h1 style="margin:4px 0">${esc(top.title)}</h1><div class="sub">${esc(top.detail)}</div>
        <a class="btn primary block" href="${API}/?job=${top.job_id}" target="_blank">Open it ↗</a>`
        : `<h1 style="margin:4px 0">Nothing due 🎉</h1><div class="sub">Open a job posting and I'll help you apply.</div>`}
    </div>
    ${q.length > 1 ? `<details><summary>${q.length - 1} more</summary>${q.slice(1, 8).map(i => `<div class="person">${esc(i.title)}<div class="muted small">${esc(i.detail)}</div></div>`).join('')}</details>` : ''}
    <p class="muted small">Tip: open a job posting or someone's LinkedIn profile and this panel switches to it.</p>`;
}


function authBanner(wa) {
  if (!wa || wa.verdict === 'unknown') return '';
  if (wa.verdict === 'dont_apply')
    return `<div class="auth bad">⛔ <b>Don't apply:</b> ${esc(wa.reason)}${wa.quote ? `<div class="quote">“${esc(wa.quote)}”</div>` : ''}</div>`;
  return wa.quote ? `<div class="auth ok">✅ ${esc(wa.reason)}<div class="quote">“${esc(wa.quote)}”</div></div>` : '';
}

// ---------- untracked job page ----------
async function renderUntrackedJob(tab, page) {
  const wa = await api('/api/work-auth', { url: tab.url, text: page.text }).catch(() => null);
  app.innerHTML = `
    <h1>New job?</h1><div class="sub">${esc(page.title)}</div>
    ${authBanner(wa)}
    <button class="btn primary block" id="saveTailor">Save + tailor my resume</button>
    <button class="btn block" id="saveOnly">Just save it</button>
    <p class="muted small">I read the description from this page, no pasting needed.</p>`;
  const save = async tailor => {
    const { id } = await api('/api/page/save-job', { url: tab.url, title: page.title, text: page.text });
    chrome.runtime.sendMessage({ type: 'remember-job', tabId: tab.id, jobId: id });
    await renderJob(id);
    if (tailor) document.querySelector('[data-tailor="A"]')?.click();
  };
  $('#saveTailor').onclick = e => busy(e.target, 'Reading the posting…', () => save(true));
  $('#saveOnly').onclick = e => busy(e.target, 'Saving…', () => save(false));
}

// ---------- tracked job: 1 tailor, 2 apply, 3 reach out ----------
async function renderJob(jobId) {
  const page = await api(`/api/jobs/${jobId}`);
  const { job, people, searches } = page;
  const pdfUrl = page.variants.A.pdf_url || page.variants.B.pdf_url;
  const applied = !['saved', 'tailoring'].includes(job.status);
  const reached = people.some(p => p.link && !['suggested', 'to_contact'].includes(p.link.status));
  const stepCls = (n) => {
    const done = [!!pdfUrl || applied, applied, reached][n - 1];
    const cur = !done && [true, !!pdfUrl || applied, applied][n - 1];
    return done ? 'done' : cur ? 'current' : '';
  };

  app.innerHTML = `
    <h1>${esc(job.company)}</h1>
    ${authBanner(job.work_auth)}
    <div class="sub">${esc(job.role)} <span class="pill ${applied ? 'good' : ''}">${esc(job.status.replace('_', ' '))}</span>
      ${job.fit_score != null ? `<span class="pill accent">fit ${job.fit_score}</span>` : ''}</div>

    <div class="step ${stepCls(1)}">
      <div class="step-title"><span class="num">1</span> Tailored resume${page.single_version ? ' <span class="pill">one version only</span>' : ''}</div>
      ${['A', 'B'].filter(v => v === 'A' || !page.single_version).map(v => {
        const x = page.variants[v];
        return `<div class="person">
          <div class="row between"><b>Version ${v}${x.score ? ` <span class="pill ${x.score.score >= 80 ? 'good' : x.score.score >= 60 ? 'warn' : ''}">match ${x.score.score}%</span>` : ''}</b><span class="muted small">${esc(x.name)} · ${esc(x.email)}</span></div>
          ${x.pdf_url ? `<div class="row"><a class="btn primary" href="${API}${x.pdf_url}&download=1">⬇ ${esc(x.filename)}</a>
              <a class="btn" href="${API}${x.pdf_url}" target="_blank">Preview</a>
              <button class="btn" data-tailor="${v}">Redo</button></div>`
            : `<button class="btn ${v === 'A' ? 'primary' : ''} block" data-tailor="${v}">✨ Tailor version ${v}</button>`}
        </div>`;
      }).join('')}
      <div class="muted small">~40s each. Same true facts, different angle + name/email per version.</div>
      <details ${pdfUrl ? 'open' : ''} style="margin-top:8px"><summary><b>💬 Tell it what to put in</b></summary>
        <div id="chatLog" class="small" style="max-height:220px;overflow-y:auto;margin-top:6px"></div>
        <textarea class="input" id="chatIn" style="min-height:70px" placeholder="e.g. use project X instead of project Y, drop GPA, frame an internship around product impact"></textarea>
        <div class="row" style="margin-top:6px">
          <select class="input" id="chatVar" style="width:auto;margin:0"><option value="A">Version A</option>${page.single_version ? '' : '<option value="B">Version B</option>'}</select>
          <button class="btn primary" id="chatSend">Send</button>
          <button class="btn" id="chatGaps">Find my gaps</button>
        </div>
      </details>
    </div>

    <div class="step ${stepCls(2)}">
      <div class="step-title"><span class="num">2</span> Apply</div>
      ${applied && job.applied_variants ? `<div class="muted">Applied ${esc(job.applied_on || '')} with ${esc(job.applied_variants.replace(',', ' + '))} ✓</div>` : ''}
      <div class="muted small">Let Simplify fill the form and upload the PDF for the email you're applying with.
      I'll notice the "thanks for applying" page.</div>
      <div class="row" style="margin-top:6px"><span class="muted small">I applied with:</span>
        <button class="btn" data-applied="A">A</button>
        ${page.single_version ? '' : '<button class="btn" data-applied="B">B</button><button class="btn" data-applied="A,B">A + B</button>'}
      </div>
    </div>

    <div class="step ${stepCls(3)}">
      <div class="step-title"><span class="num">3</span> Reach out</div>
      ${people.length ? people.slice(0, 4).map(p => `
        <div class="person">
          <div class="row between"><b>${esc(p.name)}</b>
            <span class="pill ${p.link && !['suggested', 'to_contact'].includes(p.link.status) ? 'good' : ''}">${esc(p.link?.status?.replace('_', ' ') || (p.degree === 1 ? '1st' : 'suggested'))}</span></div>
          <div class="muted small">${esc(p.title)} · ${esc((p.reasons || []).slice(0, 2).join(' · '))}</div>
          ${p.linkedin_url ? `<a class="small" href="${esc(p.linkedin_url)}" target="_blank">Open profile → I'll draft the message there</a>` : ''}
        </div>`).join('') : `<div class="muted small">No one you know here yet. Use a search below, open a profile, and I'll take it from there.</div>`}
      <button class="btn block" id="batch">Connection notes for top people (batch)</button>
      <div id="batchOut"></div>
      <details><summary>Find people on LinkedIn</summary><div class="links">
        ${searches.map(s => `<a href="${esc(s.url)}" target="_blank">${esc(s.label)}</a>`).join('')}</div></details>
    </div>`;

  const chatLog = $('#chatLog');
  const showChat = msgs => {
    chatLog.innerHTML = msgs.slice(-4).map(m => `<div class="note"><b>${m.role === 'me' ? 'You' : 'Coach'}:</b> ${esc(m.content)}</div>`).join('');
    chatLog.scrollTop = chatLog.scrollHeight;
  };
  let msgs = await api(`/api/jobs/${jobId}/resume-chat`).catch(() => []);
  showChat(msgs);
  const sendChat = (text, btn) => busy(btn, 'Thinking… ~40s', async () => {
    if (text) { msgs.push({ role: 'me', content: text }); showChat(msgs); }
    $('#chatIn').value = '';
    const r = await api(`/api/jobs/${jobId}/resume-chat`, { message: text, variant: $('#chatVar').value });
    msgs.push({ role: 'claude', content: r.reply });
    showChat(msgs);
    if (r.updated) {
      banner(r.warning ? '⚠️ ' + r.warning : `Resume updated ✓${r.score ? ` · match ${r.score.score}%` : ''}`);
      await renderJob(jobId);
    }
  });
  $('#chatSend').onclick = e => { const t = $('#chatIn').value.trim(); if (t) sendChat(t, e.target); };
  $('#chatGaps').onclick = e => sendChat('', e.target);

  document.querySelectorAll('[data-tailor]').forEach(btn => btn.onclick = e => busy(e.target, 'Tailoring… ~40s', async () => {
    const r = await api(`/api/jobs/${jobId}/tailor?variant=${btn.dataset.tailor}`, {});
    banner(r.warning ? '⚠️ ' + r.warning : `Version ${r.variant} ready: ${r.filename}`, r.warning ? 9000 : 6000);
    await renderJob(jobId);
  }));
  document.querySelectorAll('[data-applied]').forEach(btn => btn.onclick = e => busy(e.target, 'Saving…', async () => {
    await api('/api/track/applied', { job_id: jobId, variants: btn.dataset.applied.split(',') });
    banner(`Applied with ${btn.dataset.applied.replace(',', ' + ')} ✓ Now reach out 👇`);
    await renderJob(jobId);
  }));
  $('#batch').onclick = e => busy(e.target, 'Writing notes…', async () => {
    const notes = await api(`/api/jobs/${jobId}/batch-notes`, {});
    $('#batchOut').innerHTML = notes.length ? notes.map((n, i) => `
      <div class="person">
        <b>${esc(n.person.name)}</b> <span class="muted small">${esc(n.person.title)}</span>
        <div class="note">${esc(n.note)}</div>
        <div class="row">
          <button class="btn" data-copy="${i}">Copy</button>
          ${n.person.linkedin_url ? `<a class="btn" href="${esc(n.person.linkedin_url)}" target="_blank">Open profile</a>` : ''}
          ${n.over_limit ? '<span class="pill warn">over limit</span>' : ''}
        </div>
      </div>`).join('')
      : '<div class="muted small">Everyone here is already contacted or 1st-degree (open their profile for a DM).</div>';
    document.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => copy(notes[+b.dataset.copy].note));
  });
}

// ---------- LinkedIn profile ----------
// Early-career = intern / new grad / just started: short congrats note works best.
const EARLY_RE = /\b(intern|internship|incoming|new grad|graduate|associate|apm|rotational|fellow|junior|jr\.?|analyst i|engineer i|entry)\b/i;
let LANGS = [{ code: 'en', label: 'English', name_pattern: '' }];  // extra languages come from the private profile
function langOptions(name) {
  const pick = LANGS.find(l => l.name_pattern && new RegExp(l.name_pattern, 'i').test(name || ''));
  return LANGS.map(l => `<option value="${l.code}" ${pick && pick.code === l.code ? 'selected' : ''}>${l.label}</option>`).join('');
}
api('/api/languages').then(l => { if (Array.isArray(l)) LANGS = l; }).catch(() => {});
function suggestKind(person, link, jobStatus) {
  const st = link?.status;
  if (st === 'messaged' || st === 'no_reply') return 'follow_up';
  if (st === 'replied' || st === 'referred') return 'thank_you';
  if (st === 'connected' || st === 'requested' || (person.degree === 1 && !EARLY_RE.test(person.title || ''))) return 'connected_pitch';
  if (EARLY_RE.test(person.title || '')) return 'peer_congrats';
  if ((person.reasons || []).some(r => /alum/i.test(r))) return 'alumni';
  if (person.category === 'recruiter' && !['saved', 'tailoring'].includes(jobStatus)) return 'recruiter_after_apply';
  if (person.source === 'referral_sheet') return 'referral_ask';
  return person.degree === 1 ? 'connected_pitch' : 'connection_note';
}

const KIND_LABEL = {
  peer_congrats: 'Early-career: congrats + quick Qs (short)', alumni: 'Fellow alum (same school)',
  connected_pitch: 'They accepted: thanks + my pitch + availability',
  connection_note: 'Connection request note',
  referral_ask: 'Ask for a referral', recruiter_after_apply: 'Recruiter: I just applied',
  hiring_manager: 'Hiring manager intro', cold_dm: 'Cold DM / InMail', follow_up: 'Follow-up', thank_you: 'Thank you',
};

async function renderPerson(tab) {
  app.innerHTML = '<p class="muted">Reading their profile…</p>';
  const key = tab.url.split('?')[0];
  let data = personCache.get(key);
  if (!data) {
    await new Promise(r => setTimeout(r, 1200)); // LinkedIn renders late
    const page = await pageText(tab.id);
    data = await api('/api/page/person', { url: tab.url, title: page.title, text: page.text.slice(0, 8000) })
      .catch(e => ({ error: e.message }));
    if (!data.error) personCache.set(key, data);
  }
  if (data.error) { app.innerHTML = `<p>⚠️ ${esc(data.error)}</p>`; return; }
  const { person, jobs } = data;
  if (!person) { app.innerHTML = '<p class="muted">Couldn\'t read this profile. Scroll a bit and reopen the panel.</p>'; return; }

  const degree = person.degree === 1 ? '1st' : person.degree === 2 ? '2nd' : person.degree === 3 ? '3rd' : '';
  app.innerHTML = `
    <h1>${esc(person.name)}</h1>
    <div class="sub">${esc(person.title)}${person.company ? ` @ ${esc(person.company)}` : ''} ${degree ? `<span class="pill accent">${degree}</span>` : ''}</div>
    ${!jobs.length ? `<div class="step"><div class="muted">You're not tracking a job at ${esc(person.company || 'their company')}.
        Save one from a posting first, then come back.</div></div>` : `
    <div class="step current">
      <label class="small muted">For</label>
      <select class="input" id="jobSel">${jobs.map((j, i) => `<option value="${i}">${esc(j.job.role)} @ ${esc(j.job.company)}</option>`).join('')}</select>
      <div id="why" class="small muted" style="margin-top:6px"></div>
      <select class="input" id="kind">${meta.message_kinds.map(k => `<option value="${k}">${KIND_LABEL[k] || k}</option>`).join('')}</select>
      <div class="row small" style="margin-top:6px">
        <select class="input" id="lang" style="width:auto;margin:0">${langOptions(person.name)}</select>
        <label class="row"><input type="checkbox" id="notopen"> Role isn't open yet</label>
      </div>
      <input class="input" id="hook" placeholder="Why them? A post, their path, a shared thing (optional)">
      <button class="btn primary block" id="gen">Write it in my voice</button>
      <textarea class="input" id="draft" placeholder="Draft shows up here. Edit freely."></textarea>
      <div class="row between small"><span id="count" class="muted"></span><button class="btn" id="copy">Copy</button></div>
      <div class="muted small" id="whyWorks"></div>
      <div class="row" style="margin-top:6px"><input class="input" id="tone" style="margin:0;flex:1" placeholder="Tone fix for next time">
        <button class="btn" id="remember">Remember</button></div>
      <div class="row" style="margin-top:8px">
        <button class="btn" id="sentReq">I sent a connection request</button>
        <button class="btn" id="sentMsg">I sent the message</button>
      </div>
      <div class="muted small">Clicking Send on LinkedIn logs it automatically. These buttons are the backup.</div>
    </div>`}`;
  if (!jobs.length) return;

  const limit = meta.me.connection_note_limit || 200;
  const sel = $('#jobSel'), kind = $('#kind'), draft = $('#draft');
  const pick = () => {
    const j = jobs[+sel.value];
    $('#why').textContent = (j.reasons || []).join(' · ');
    kind.value = suggestKind({ ...person, reasons: j.reasons, category: j.category }, j.link, j.job.status);
    $('#notopen').checked = !j.job.url;
  };
  const count = () => {
    const n = draft.value.length;
    $('#count').innerHTML = kind.value === 'connection_note' ? `${n} / ${limit}${n > limit ? ' <b style="color:var(--bad)">too long</b>' : ''}` : `${n} chars`;
  };
  sel.onchange = pick; draft.oninput = count; kind.onchange = count;
  pick();
  $('#gen').onclick = e => busy(e.target, 'Writing…', async () => {
    const j = jobs[+sel.value];
    const r = await api(`/api/jobs/${j.job.id}/people/${person.id}/draft`, { kind: kind.value, personalization: $('#hook').value, tier: 1,
      language: $('#lang').value, not_open: $('#notopen').checked });
    draft.value = (r.subject ? `Subject: ${r.subject}\n\n` : '') + r.draft;
    $('#whyWorks').textContent = r.why_this_works || '';
    count();
  });
  $('#copy').onclick = () => copy(draft.value);
  $('#remember').onclick = async () => {
    const t = $('#tone').value.trim();
    if (!t) return;
    await api('/api/voice/note', { text: t });
    $('#tone').value = '';
    banner('Got it, future drafts follow that ✓');
  };
  const log = kindName => async e => busy(e.target, 'Logging…', async () => {
    const j = jobs[+sel.value];
    await api('/api/track/outreach', { linkedin_url: person.linkedin_url, job_id: j.job.id, kind: kindName, message: draft.value });
    personCache.delete(key);
    banner('Logged ✓');
  });
  $('#sentReq').onclick = log('requested');
  $('#sentMsg').onclick = log('messaged');
}

// ---------- wiring ----------
chrome.tabs.onActivated.addListener(() => refresh());
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (tab.active && (info.status === 'complete' || info.url)) setTimeout(() => refresh(), info.url ? 800 : 0);
});
chrome.runtime.onMessage.addListener(msg => {
  if (msg.type !== 'tracked') return;
  banner(msg.text);
  personCache.clear();
  refresh(true);
});
refresh(true);
