'use strict';

// ---------- tiny helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.body && !(opts.body instanceof FormData)) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}

function toast(msg, ms = 2200) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), ms);
}

async function copy(text, label = 'Copied') {
  await navigator.clipboard.writeText(text);
  toast(`${label} ✓`);
}

async function busy(btn, label, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  try { return await fn(); }
  catch (e) { toast(e.message, 5000); throw e; }
  finally { btn.disabled = false; btn.textContent = old; }
}

const STATUS_LABEL = {
  saved: 'Saved', tailoring: 'Tailoring', applied: 'Applied', reached_out: 'Reached out',
  interviewing: 'Interviewing', offer: 'Offer', rejected: 'Rejected', archived: 'Archived',
};
const STATUS_CLASS = { applied: 'accent', reached_out: 'accent', interviewing: 'good', offer: 'good', rejected: 'bad' };
const CONTACT_LABEL = {
  suggested: 'Suggested', to_contact: 'To contact', requested: 'Request sent', connected: 'Accepted, DM them',
  messaged: 'Messaged', replied: 'Replied',
  referred: 'Referred me!', no_reply: 'No reply',
};
const KIND_LABEL = {
  peer_congrats: 'Early-career: congrats + quick Qs (short)', alumni: 'Fellow alum (same school)',
  connected_pitch: 'They accepted: thanks + my pitch + availability',
  connection_note: 'Connection note', referral_ask: 'Ask for referral', recruiter_after_apply: 'Recruiter: I just applied',
  hiring_manager: 'Hiring manager intro', cold_dm: 'Cold DM', follow_up: 'Follow-up', thank_you: 'Thank you',
};

// ---------- state ----------
const state = { meta: null, jobs: [], filter: 'active', q: '', openJob: null, drawerTab: null, queue: [], skip: 0, profileFile: 'resume' };

// ---------- navigation ----------
function showView(v) {
  $$('#mainTabs button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  $$('.view').forEach(s => s.classList.toggle('hidden', s.id !== `view-${v}`));
  if (v === 'people') loadPeople();
  if (v === 'profile') loadProfile();
}
$$('#mainTabs button').forEach(b => b.onclick = () => showView(b.dataset.view));

// ---------- board ----------
async function loadMeta() {
  state.meta = await api('/api/meta');
  const f = state.meta.profile_files;
  const missing = [];
  if (!f.resume.filled) missing.push('your master resume');
  if (!f.voice.filled) missing.push('your writing voice');
  if (!state.meta.people_count) missing.push('your LinkedIn connections');
  const n = $('#setupNudge');
  if (missing.length) {
    n.innerHTML = `<b>Setup:</b> add ${missing.length > 1 ? missing.slice(0, -1).join(', ') + ' and ' + missing.at(-1) : missing[0]} so tailoring and people-ranking work. <a href="#" id="goSetup">Do it now →</a>`;
    n.classList.remove('hidden');
    $('#goSetup').onclick = e => { e.preventDefault(); showView(!f.resume.filled || !f.voice.filled ? 'profile' : 'people'); };
  } else n.classList.add('hidden');
}

async function loadBoard() {
  let ab;
  [state.jobs, state.queue, ab] = await Promise.all([api('/api/jobs'), api('/api/nextup'), api('/api/ab-stats')]);
  const fmt = x => `${x.replies}/${x.sent} replied${x.rate != null ? ` (${x.rate}%)` : ''}`;
  $('#abStats').innerHTML = ab.A.sent || ab.B.sent ? `A/B: <b>A</b> ${fmt(ab.A)} · <b>B</b> ${fmt(ab.B)}` : '';
  renderNextUp();
  renderJobs();
}

function renderNextUp() {
  const q = state.queue;
  const body = $('#nextupBody');
  if (!q.length) {
    body.innerHTML = state.jobs.length
      ? `<div class="nextup-title">You're caught up 🎉</div><div class="nextup-detail">Nothing due. Add another role, or take a break.</div>`
      : `<div class="nextup-title">Add your first role</div><div class="nextup-detail">Paste a job posting. Everything else starts from there.</div>
         <button class="btn primary big" onclick="openAdd()">+ Add role</button>`;
    return;
  }
  const i = state.skip % q.length;
  const item = q[i];
  const actionLabel = { follow_up: 'Write the follow-up', reach_out: 'Pick who to message', tailor: 'Tailor resume', apply: 'Open resume + apply link', stale: 'Open it', learn: 'See what to learn' }[item.kind];
  body.innerHTML = `
    <div class="nextup-title">${esc(item.title)}</div>
    <div class="nextup-detail">${esc(item.detail)}</div>
    <div class="row gap">
      <button class="btn primary big" id="nuGo">${actionLabel} →</button>
      ${q.length > 1 ? '<button class="btn" id="nuSkip">Not now</button>' : ''}
    </div>
    ${q.length > 1 ? `<details class="nextup-more"><summary>${q.length - 1} more after this</summary><ol>${
      q.filter((_, k) => k !== i).map(x => `<li data-job="${x.job_id}" data-kind="${x.kind}">${esc(x.title)}</li>`).join('')
    }</ol></details>` : ''}`;
  $('#nuGo').onclick = () => openJob(item.job_id, ['tailor', 'apply', 'learn'].includes(item.kind) ? 'resume' : 'people', item);
  const skip = $('#nuSkip');
  if (skip) skip.onclick = () => { state.skip++; renderNextUp(); };
  $$('.nextup-more li').forEach(li => li.onclick = () =>
    openJob(+li.dataset.job, ['tailor', 'apply'].includes(li.dataset.kind) ? 'resume' : 'people'));
}

function matchesFilter(j) {
  const done = ['rejected', 'archived'].includes(j.status);
  switch (state.filter) {
    case 'active': return !done && !(j.priority === 3 && ['saved', 'tailoring'].includes(j.status));
    case 'inbox': return j.priority === 3 && ['saved', 'tailoring'].includes(j.status);
    case 'todo': return ['saved', 'tailoring'].includes(j.status);
    case 'applied': return ['applied', 'reached_out', 'interviewing', 'offer'].includes(j.status);
    case 'gap': return !done && j.coverage === 'gap';
    default: return true;
  }
}

function peopleCell(j) {
  if (j.replied) return `<span class="pill good">${j.replied} replied</span>`;
  if (j.coverage === 'strong') return `<span class="pill good">● ${j.warm_count} · ${esc(j.best_person)}</span>`;
  if (j.coverage === 'weak') return `<span class="pill warn">● ${j.warm_count} · ${esc(j.best_person)}</span>`;
  return `<span class="pill bad">none yet, find</span>`;
}

function renderJobs() {
  const q = state.q.toLowerCase();
  const list = state.jobs.filter(matchesFilter).filter(j => !q || `${j.company} ${j.role} ${j.location}`.toLowerCase().includes(q));
  $('#emptyBoard').classList.toggle('hidden', state.jobs.length > 0);
  const today = new Date().toISOString().slice(0, 10);
  $('#jobRows').innerHTML = list.map(j => `
    <tr data-id="${j.id}" class="${['rejected', 'archived'].includes(j.status) ? 'dim' : ''}">
      <td><span class="prio p${j.priority}" title="${j.priority === 1 ? 'High priority' : ''}"></span></td>
      <td class="company">${esc(j.company)}</td>
      <td>${esc(j.role)}${j.location ? `<div class="muted small">${esc(j.location)}</div>` : ''}</td>
      <td>${j.work_auth?.verdict === 'dont_apply' ? `<span class="pill bad" title="${esc(j.work_auth.reason + ' ' + j.work_auth.quote)}">⛔ Not for F-1</span> ` : ''}<span class="pill ${STATUS_CLASS[j.status] || ''}">${STATUS_LABEL[j.status]}</span>${j.applied_variants ? ` <span class="muted small">${esc(j.applied_variants.replace(',', '+'))}</span>` : ''}</td>
      <td>${j.fit_score != null ? `<span class="pill ${j.fit_score >= 70 ? 'good' : j.fit_score >= 45 ? 'warn' : 'bad'}">${j.fit_score}</span>` : '<span class="muted">–</span>'}</td>
      <td>${peopleCell(j)}</td>
      <td>${j.contacted ? j.contacted : '<span class="muted">0</span>'}</td>
      <td>${j.follow_up_on ? `<span class="${j.follow_up_on <= today ? 'pill warn' : 'muted'}">${j.follow_up_on}</span>` : ''}</td>
    </tr>`).join('');
  $$('#jobRows tr').forEach(tr => tr.onclick = () => {
    const j = state.jobs.find(x => x.id === +tr.dataset.id);
    openJob(j.id, ['saved', 'tailoring'].includes(j.status) ? 'resume' : 'people');
  });
}

$$('#filters .chip').forEach(c => c.onclick = () => {
  state.filter = c.dataset.filter;
  $$('#filters .chip').forEach(x => x.classList.toggle('active', x === c));
  renderJobs();
});
$('#search').oninput = e => { state.q = e.target.value; renderJobs(); };
$('#pullLatest').onclick = e => busy(e.target, 'Pulling newest roles… (~1-2 min)', async () => {
  const r = await api('/api/roles/pull-latest?limit=100', { method: 'POST' });
  toast(`Added ${r.added} new roles to "New roles" (${r.already_had} already on your board, ${r.not_for_f1} flagged not eligible for your work authorization). Set priority to promote one.`, 7000);
  state.filter = 'inbox';
  $$('#filters .chip').forEach(x => x.classList.toggle('active', x.dataset.filter === 'inbox'));
  await loadBoard();
});

// ---------- drawer ----------
async function openJob(id, tab, nextItem) {
  state.openJob = await api(`/api/jobs/${id}`);
  state.drawerTab = tab || state.drawerTab || 'people';
  state.nextItem = nextItem || null;
  const { job } = state.openJob;
  $('#dCompany').textContent = job.company;
  $('#dRole').textContent = job.role + (job.location ? ` · ${job.location}` : '');
  $('#dLinks').innerHTML = job.url ? `<a href="${esc(job.url)}" target="_blank" rel="noopener">Job posting ↗</a>` : '';
  const wa = job.work_auth;
  $('#dAuth').innerHTML = !wa || wa.verdict === 'unknown' ? ''
    : wa.verdict === 'dont_apply'
      ? `<div class="auth bad">⛔ <b>Don't apply:</b> ${esc(wa.reason)}${wa.quote ? `<div class="quote">“${esc(wa.quote)}”</div>` : ''}</div>`
      : wa.quote ? `<div class="auth ok">✅ ${esc(wa.reason)}<div class="quote">“${esc(wa.quote)}”</div></div>` : '';
  const sel = $('#dStatus');
  sel.innerHTML = state.meta.statuses.map(s => `<option value="${s}" ${s === job.status ? 'selected' : ''}>${STATUS_LABEL[s]}</option>`).join('');
  sel.onchange = async () => {
    await api(`/api/jobs/${id}`, { method: 'PATCH', body: { status: sel.value } });
    toast(sel.value === 'applied' ? 'Applied ✓ Now message someone 👇' : 'Saved');
    if (sel.value === 'applied') state.drawerTab = 'people';
    await openJob(id, state.drawerTab);
    loadBoard();
  };
  $('#drawer').classList.remove('hidden');
  $('#scrim').classList.remove('hidden');
  renderDrawer();
}

function closeDrawer() {
  $('#drawer').classList.add('hidden');
  $('#scrim').classList.add('hidden');
  state.openJob = null;
}
$('#closeDrawer').onclick = closeDrawer;
$('#scrim').onclick = closeDrawer;
$$('#drawerTabs button').forEach(b => b.onclick = () => { state.drawerTab = b.dataset.tab; renderDrawer(); });

function renderDrawer() {
  $$('#drawerTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === state.drawerTab));
  ({ people: renderPeopleTab, resume: renderResumeTab, overview: renderOverviewTab, log: renderLogTab })[state.drawerTab]();
}

// People & messages
function renderPeopleTab() {
  const { job, people, searches } = state.openJob;
  const body = $('#drawerBody');
  const applied = !['saved', 'tailoring'].includes(job.status);
  body.innerHTML = `
    ${!applied ? `<p class="muted small">Tip: apply first, then message. "I just applied to X" is the easiest opener there is.</p>` : ''}
    <div class="section-title">Best people to message (${people.length})</div>
    ${people.length ? people.map((p, i) => personCard(p, i === 0)).join('') :
      `<div class="card muted">No one you know at ${esc(job.company)} yet. Use the searches below, then add the people you find.</div>`}

    <div class="section-title">Connection requests in bulk</div>
    <button class="btn" id="batchBtn">Write connection notes for the top people I'm not connected to</button>
    <div id="batchOut"></div>

    <div class="section-title">Find more people on LinkedIn</div>
    <div class="links">${searches.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)} ↗<span class="why">${esc(s.why)}</span></a>`).join('')}</div>
    <p class="muted small">Tip: set the LinkedIn company ID in <b>Job &amp; fit</b> for exact company filtering.</p>

    <div class="section-title">Add someone you found</div>
    <form id="addPerson" class="card">
      <div class="grid2">
        <label>Name<input class="input" name="name" required></label>
        <label>Title<input class="input" name="title"></label>
        <label>LinkedIn URL<input class="input" name="linkedin_url"></label>
        <label>Connection<select class="input" name="degree"><option value="">Unknown</option><option value="1">1st</option><option value="2">2nd</option><option value="3">3rd+</option></select></label>
      </div>
      <label class="muted small">What you have in common (school, ex-coworker, same club, their post you liked…)
        <input class="input" name="relationship"></label>
      <div class="row end" style="margin-top:10px"><button class="btn primary">Add</button></div>
    </form>`;

  $('#batchBtn').onclick = e => busy(e.target, 'Writing notes…', async () => {
    const notes = await api(`/api/jobs/${job.id}/batch-notes`, { method: 'POST' });
    $('#batchOut').innerHTML = notes.length ? notes.map((n, i) => `
      <div class="person"><b>${esc(n.person.name)}</b> <span class="muted small">${esc(n.person.title)}</span>
        <div class="small" style="margin:6px 0;white-space:pre-wrap">${esc(n.note)}</div>
        <div class="row gap"><button class="btn" data-copy="${i}">Copy</button>
        ${n.person.linkedin_url ? `<a class="btn" href="${esc(n.person.linkedin_url)}" target="_blank" rel="noopener">Open profile ↗</a>` : ''}
        ${n.over_limit ? '<span class="pill warn">over limit</span>' : ''}</div></div>`).join('')
      : '<p class="muted">Everyone here is already contacted or a 1st-degree connection.</p>';
    $$('[data-copy]').forEach(b => b.onclick = () => copy(notes[+b.dataset.copy].note));
  });

  $('#addPerson').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    f.degree = f.degree ? +f.degree : null;
    await api(`/api/jobs/${job.id}/people`, { method: 'POST', body: f });
    toast('Added');
    await openJob(job.id, 'people');
    loadBoard();
  };

  $$('.person').forEach(card => {
    const pid = +card.dataset.id;
    const person = people.find(p => p.id === pid);
    $('.contact-status', card).onchange = async e => {
      await api(`/api/jobs/${job.id}/people/${pid}`, { method: 'PUT', body: { status: e.target.value } });
      toast(e.target.value === 'referred' ? 'Amazing 🎉' : 'Saved');
      await openJob(job.id, 'people');
      loadBoard();
    };
    $('.draft-btn', card).onclick = () => openComposer(card, job, person);
  });

  // Coming from "Next up: follow up with X": jump straight into the composer.
  if (state.nextItem?.person_id) {
    const card = $(`.person[data-id="${state.nextItem.person_id}"]`);
    if (card) openComposer(card, job, people.find(p => p.id === state.nextItem.person_id), state.nextItem);
    state.nextItem = null;
  }
}

function personCard(p, top) {
  const st = p.link?.status || 'suggested';
  return `
  <div class="person ${top ? 'best' : ''}" data-id="${p.id}">
    <div class="person-head">
      <div>
        <div class="person-name">${esc(p.name)} ${p.linkedin_url ? `<a href="${esc(p.linkedin_url)}" target="_blank" rel="noopener" class="small">LinkedIn ↗</a>` : ''}</div>
        <div class="muted small">${esc(p.title || '')}${p.company ? ` · ${esc(p.company)}` : ''}</div>
      </div>
      <div class="row gap">
        <span class="pill ${top ? 'accent' : ''}" title="Reply-likelihood score">${p.score}</span>
        <select class="input contact-status">${state.meta.contact_statuses.map(s => `<option value="${s}" ${s === st ? 'selected' : ''}>${CONTACT_LABEL[s]}</option>`).join('')}</select>
      </div>
    </div>
    <div class="reasons">${(p.reasons || []).map(r => `<span class="pill">${esc(r)}</span>`).join('')}</div>
    ${p.link?.last_message ? `<div class="muted small">Last sent ${esc(p.link.messaged_on || '')}: “${esc(p.link.last_message.slice(0, 140))}${p.link.last_message.length > 140 ? '…' : ''}”</div>` : ''}
    <div class="row gap" style="margin-top:6px"><button class="btn draft-btn">✍️ Draft a message</button></div>
    <div class="composer-slot"></div>
  </div>`;
}

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
const defaultKind = (job, person) => suggestKind(person, person.link, job.status);

function openComposer(card, job, person, nextItem) {
  const slot = $('.composer-slot', card);
  if (slot.innerHTML && !nextItem) { slot.innerHTML = ''; return; }
  const kind = nextItem?.message_kind || defaultKind(job, person);
  const limit = state.meta.me.connection_note_limit || 200;
  slot.innerHTML = `
    <div class="composer">
      <div class="row gap wrap">
        <select class="input kind">${state.meta.message_kinds.map(k => `<option value="${k}" ${k === kind ? 'selected' : ''}>${KIND_LABEL[k]}</option>`).join('')}</select>
        <select class="input tier ${kind === 'follow_up' ? '' : 'hidden'}">
          ${[1, 2, 3].map(t => `<option value="${t}" ${t === (nextItem?.tier || 1) ? 'selected' : ''}>Follow-up #${t}</option>`).join('')}
        </select>
      </div>
      <div class="row gap wrap small">
        <select class="input lang">${langOptions(person.name)}</select>
        <label class="row gap"><input type="checkbox" class="notopen" ${!job.url && !job.jd ? 'checked' : ''}> Role isn't open yet</label>
      </div>
      <input class="input personalization" placeholder="Why them? (a post of theirs, shared thing, mutual…). Optional but boosts replies a lot.">
      <button class="btn primary gen">Generate in my voice</button>
      <textarea class="input draft-box" placeholder="Your draft appears here. Edit freely."></textarea>
      <div class="row between small"><span class="muted count"></span><span class="muted why"></span></div>
      <div class="row gap"><input class="input tone" placeholder="Tone fix for next time, e.g. fewer emojis with senior people">
        <button class="btn remember">Remember</button></div>
      <div class="row gap wrap">
        <button class="btn copy">Copy</button>
        ${person.linkedin_url ? `<a class="btn" href="${esc(person.linkedin_url)}" target="_blank" rel="noopener">Open their LinkedIn ↗</a>` : ''}
        <button class="btn primary sent">I sent it ✓</button>
      </div>
    </div>`;
  const box = $('.draft-box', slot);
  const kindSel = $('.kind', slot);
  const count = () => {
    const n = box.value.length;
    const over = kindSel.value === 'connection_note' && n > limit;
    $('.count', slot).innerHTML = `${n} chars${kindSel.value === 'connection_note' ? ` / ${limit}` : ''}${over ? ' <b style="color:var(--bad)">too long</b>' : ''}`;
  };
  box.oninput = count;
  kindSel.onchange = () => $('.tier', slot).classList.toggle('hidden', kindSel.value !== 'follow_up');
  $('.gen', slot).onclick = e => busy(e.target, 'Writing…', async () => {
    const r = await api(`/api/jobs/${job.id}/people/${person.id}/draft`, {
      method: 'POST',
      body: { kind: kindSel.value, personalization: $('.personalization', slot).value, tier: +$('.tier', slot).value,
              language: $('.lang', slot).value, not_open: $('.notopen', slot).checked },
    });
    box.value = (r.subject ? `Subject: ${r.subject}\n\n` : '') + r.draft;
    $('.why', slot).textContent = r.why_this_works || '';
    if (r.warning) toast(r.warning, 4000);
    count();
  });
  $('.copy', slot).onclick = () => copy(box.value);
  $('.remember', slot).onclick = async () => {
    const t = $('.tone', slot).value.trim();
    if (!t) return;
    await api('/api/voice/note', { method: 'POST', body: { text: t } });
    $('.tone', slot).value = '';
    toast('Got it, every future draft follows that ✓');
  };
  $('.sent', slot).onclick = async () => {
    await api(`/api/jobs/${job.id}/people/${person.id}`, { method: 'PUT', body: { status: 'messaged', message: box.value } });
    toast("Logged. I'll remind you to follow up in 4 days.");
    await openJob(job.id, 'people');
    loadBoard();
  };
}

// Resume
function renderResumeTab() {
  const { job, variants, single_version } = state.openJob;
  if (single_version) state.variant = 'A';
  const v = state.variant || 'A';
  const cur = variants[v];
  const tex = v === 'A' ? job.tailored_resume : job.tailored_resume_b;
  const sent = (job.applied_variants || '').split(',').filter(Boolean);
  const body = $('#drawerBody');
  body.innerHTML = `
    <div class="row gap wrap" style="margin-bottom:10px">
      ${['A', 'B'].map(x => `<button class="chip ${x === v ? 'active' : ''}" data-variant="${x}" ${x === 'B' && single_version ? 'disabled title="One-version company"' : ''}>
        Version ${x}${variants[x].pdf_url ? ' ✓' : ''}${sent.includes(x) ? ' · sent' : ''}<span class="small"> · ${esc(variants[x].name)} · ${esc(variants[x].email || 'no email set')}</span></button>`).join('')}
      ${single_version ? `<span class="muted small">${esc(job.company)} is on your one-version list, so send A only.</span>` : ''}
    </div>
    <div class="row gap wrap">
      <button class="btn primary" id="tailorBtn">${tex ? `Re-tailor version ${v}` : `✨ Tailor version ${v}`}</button>
      ${!single_version && !variants.A.pdf_url && !variants.B.pdf_url ? `<button class="btn" id="tailorBoth">Tailor A + B</button>` : ''}
      ${cur.pdf_url ? `<a class="btn" href="${cur.pdf_url}&download=1">⬇ ${esc(cur.filename)}</a><a class="btn" href="/api/jobs/${job.id}/resume.tex?variant=${v}">.tex</a>` : ''}
      ${job.url ? `<a class="btn" href="${esc(job.url)}" target="_blank" rel="noopener">Open application ↗</a>` : ''}
    </div>
    ${variants.A.pdf_url || variants.B.pdf_url ? `<div class="row gap wrap" style="margin-top:8px"><span class="muted small">I applied with:</span>
      ${variants.A.pdf_url ? `<button class="btn" data-applied="A">A</button>` : ''}
      ${variants.B.pdf_url ? `<button class="btn" data-applied="B">B</button>` : ''}
      ${variants.A.pdf_url && variants.B.pdf_url ? `<button class="btn" data-applied="A,B">A + B</button>` : ''}</div>` : ''}
    ${!job.jd ? `<p class="nudge small" style="margin-top:12px">No job description saved. Paste it in <b>Job &amp; fit</b> for a much better tailor.</p>` : ''}
    <div id="tailorNotes"></div>
    ${job.stretch_skills?.length ? `<div class="nudge small" style="margin-top:12px">📚 <b>Learn before your interview</b> (listed in Skills, not used yet): ${job.stretch_skills.map(esc).join(', ')}</div>` : ''}

    <div class="section-title">💬 Resume chat, version ${v}</div>
    <p class="muted small" style="margin:-4px 0 6px">Tell it what to put in or take out, e.g. "use project X instead of project Y", "drop the GPA", "frame my internship as ops analytics". It rebuilds the PDF.</p>
    <div class="chat card">
      <div id="chatLog" class="chat-log"></div>
      <div id="chatFacts"></div>
      <textarea class="input" id="chatInput" rows="3" placeholder="e.g. Include my startup work but frame it around customer research. Or just answer its questions."></textarea>
      <div class="row gap" style="margin-top:8px">
        <button class="btn primary" id="chatSend">Send</button>
        <button class="btn" id="chatGaps">Find my gaps for this job</button>
        <span class="muted small">⌘↵ to send</span>
      </div>
    </div>


    ${cur.score ? `<div class="section-title">Match score, version ${v}</div>
      <div class="row gap wrap"><span class="pill ${cur.score.score >= 80 ? 'good' : cur.score.score >= 60 ? 'warn' : 'bad'}" style="font-size:14px">${cur.score.score}% of must-have keywords</span>
      ${cur.score.missing.length ? `<span class="muted small">Missing (click to ask the chat):</span>${cur.score.missing.map(k => `<button class="chip" data-missing="${esc(k)}">${esc(k)}</button>`).join('')}` : '<span class="muted small">Covers every must-have keyword 🎉</span>'}</div>` : ''}

    <details ${job.fit?.experience_ranking?.length ? '' : 'open'} style="margin-top:14px"><summary class="section-title" style="cursor:pointer">✅ Or tick what goes in (scored for this job)</summary>
    ${job.fit?.experience_ranking?.length ? `
      <div class="card" style="padding:10px 14px">
        <div class="row gap wrap small" style="margin-bottom:8px">
          <span class="muted">Base wording on</span>
          <select class="input" id="baseVersion" style="max-width:340px"><option value="">Best of all versions</option>${(state.meta.resume_versions || []).map(x => `<option>${esc(x)}</option>`).join('')}</select>
        </div>
        <table class="jobs picks"><thead><tr><th>Use</th><th>Experience</th><th>Score</th><th>How to frame it (edit freely, e.g. "use version H bullets")</th></tr></thead><tbody>
        ${job.fit.experience_ranking.map((r, i) => `<tr>
          <td><input type="checkbox" data-pick="${i}" ${r.include ? 'checked' : ''}></td>
          <td><b>${esc(r.experience)}</b><div class="muted small">${esc(r.kind)}</div></td>
          <td><span class="pill ${r.score >= 70 ? 'good' : r.score >= 45 ? 'warn' : ''}">${r.score}</span></td>
          <td><input class="input" data-how="${i}" value="${esc(r.how)}"></td></tr>`).join('')}
        </tbody></table>
        <input class="input" id="picksNote" placeholder="Anything else? e.g. no GPA, 3 bullets max for my latest internship, put Projects above Leadership" style="margin-top:8px">
        <div class="row gap" style="margin-top:8px"><button class="btn primary" id="rebuildPicks">Rebuild version ${v} with my picks</button>
          <button class="btn" id="rescore">Re-score</button></div>
      </div>`
    : `<p class="muted small">Score every role and project you have for this job, then tick what goes in.</p>
       <button class="btn" id="rescore">Score my experiences for this job (~20s)</button>`}
    </details>

    ${cur.pdf_url ? `<div class="section-title">Preview, version ${v}</div><iframe src="${cur.pdf_url}#view=FitH" style="width:100%;height:640px;border:1px solid var(--border);border-radius:8px;background:#fff"></iframe>` : ''}
    ${tex ? `<details style="margin-top:12px"><summary class="muted">Edit the LaTeX by hand</summary>
      <textarea class="editor" id="resumeText">${esc(tex)}</textarea>
      <div class="row gap"><button class="btn" id="recompile">Save + rebuild PDF</button></div></details>` : ''}`;

  $$('[data-variant]').forEach(c => c.onclick = () => { if (c.disabled) return; state.variant = c.dataset.variant; renderResumeTab(); });

  const showNotes = rs => {
    $('#tailorNotes').innerHTML = rs.map(r => `
      ${r.warning ? `<p class="nudge small">Version ${r.variant}: ${esc(r.warning)}</p>` : ''}
      <div class="section-title">Version ${r.variant}: what changed</div><ul>${r.changes.map(c => `<li>${esc(c)}</li>`).join('')}</ul>
      ${r.stretch_skills?.length ? `<div class="section-title">Stretch skills added (learn these)</div><ul>${r.stretch_skills.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}
      ${r.cut_to_fit?.length ? `<div class="section-title">Cut to fit one page</div><ul>${r.cut_to_fit.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}
      ${r.gaps_not_added.length ? `<div class="section-title">Gaps (deliberately NOT added)</div><ul>${r.gaps_not_added.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}`).join('');
  };
  $('#tailorBtn').onclick = e => busy(e.target, `Tailoring ${v}… (~40s)`, async () => {
    const r = await api(`/api/jobs/${job.id}/tailor?variant=${v}`, { method: 'POST' });
    await openJob(job.id, 'resume');
    showNotes([r]);
    loadBoard();
  });
  const both = $('#tailorBoth');
  if (both) both.onclick = e => busy(e.target, 'Tailoring A + B… (~60s)', async () => {
    const rs = await Promise.all(['A', 'B'].map(x => api(`/api/jobs/${job.id}/tailor?variant=${x}`, { method: 'POST' })));
    await openJob(job.id, 'resume');
    showNotes(rs);
    loadBoard();
  });
  $$('[data-applied]').forEach(btn => btn.onclick = async () => {
    await api('/api/track/applied', { method: 'POST', body: { job_id: job.id, variants: btn.dataset.applied.split(',') } });
    toast(`Applied with ${btn.dataset.applied.replace(',', ' + ')} ✓ Now message someone 👇`);
    await openJob(job.id, 'people');
    loadBoard();
  });
  wireResumeChat(job, v);

  $$('[data-missing]').forEach(c => c.onclick = () => {
    $('#chatInput').value = `The JD wants "${c.dataset.missing}". Did I do anything that honestly counts? If it's in my materials, work it in where it's true. If not, ask me.`;
    $('#chatInput').focus();
  });
  $('#rescore').onclick = e => busy(e.target, 'Scoring… (~20s)', async () => {
    await api(`/api/jobs/${job.id}/fit`, { method: 'POST' });
    await openJob(job.id, 'resume');
    loadBoard();
  });
  const rb = $('#rebuildPicks');
  if (rb) rb.onclick = e => busy(e.target, 'Rebuilding… (~60s)', async () => {
    const picks = job.fit.experience_ranking.map((r, i) => ({
      experience: r.experience, include: $(`[data-pick="${i}"]`).checked, how: $(`[data-how="${i}"]`).value }));
    const r = await api(`/api/jobs/${job.id}/rebuild-with-picks`, { method: 'POST',
      body: { variant: v, picks, base_version: $('#baseVersion').value, note: $('#picksNote').value } });
    await openJob(job.id, 'resume');
    toast(r.warning || (r.score ? `Rebuilt ✓ Match score ${r.score.score}%` : 'Rebuilt ✓'), 4000);
    loadBoard();
  });

  const rc = $('#recompile');
  if (rc) rc.onclick = e => busy(e.target, 'Building…', async () => {
    const r = await api(`/api/jobs/${job.id}/recompile?variant=${v}`, { method: 'POST', body: { text: $('#resumeText').value } });
    toast(r.warning || 'PDF rebuilt ✓', r.warning ? 6000 : 2000);
    await openJob(job.id, 'resume');
  });
}

function showFacts(job, facts) {
  const box = $('#chatFacts');
  if (!box || !facts.length) return;
  box.innerHTML = `<div class="nudge small"><b>New things I learned about you:</b><ul>${facts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
    <button class="btn" id="saveFacts">Save to my narratives (future resumes use them)</button></div>`;
  $('#saveFacts').onclick = async () => {
    await api(`/api/jobs/${job.id}/save-facts`, { method: 'POST', body: { facts } });
    box.innerHTML = '';
    toast('Saved to profile/experience.md ✓');
  };
}

async function wireResumeChat(job, variant = 'A') {
  const log = $('#chatLog');
  const render = msgs => {
    log.innerHTML = msgs.length ? msgs.map(m => `<div class="msg ${m.role}"><div class="who">${m.role === 'me' ? 'You' : 'Coach'}</div><div>${esc(m.content)}</div></div>`).join('')
      : '<p class="muted small">Hit <b>Find my gaps</b> and it will ask what you did that isn\'t on paper yet.</p>';
    log.scrollTop = log.scrollHeight;
  };
  let msgs = await api(`/api/jobs/${job.id}/resume-chat`);
  render(msgs);

  const send = async (text, btn) => busy(btn, 'Thinking… (~30s)', async () => {
    if (text) { msgs.push({ role: 'me', content: text }); render(msgs); }
    $('#chatInput').value = '';
    const r = await api(`/api/jobs/${job.id}/resume-chat`, { method: 'POST', body: { message: text, variant } });
    msgs.push({ role: 'claude', content: r.reply });
    render(msgs);
    if (r.updated) {
      toast(r.warning || (r.score ? `Resume updated ✓ Match score ${r.score.score}%` : 'Resume updated ✓'), r.warning ? 6000 : 3000);
      await openJob(job.id, 'resume'); // re-renders this tab (new PDF + chat)
      loadBoard();
    }
    showFacts(job, r.new_facts || []);
  });
  $('#chatSend').onclick = e => { const t = $('#chatInput').value.trim(); if (t) send(t, e.target); };
  $('#chatGaps').onclick = e => send('', e.target);
  $('#chatInput').onkeydown = e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#chatSend').click(); };
}

// Job & fit
function renderOverviewTab() {
  const { job } = state.openJob;
  const fit = job.fit;
  const lvl = { STRONG: 'good', PARTIAL: 'warn', GAP: 'bad' };
  $('#drawerBody').innerHTML = `
    <div class="row gap"><button class="btn primary" id="fitBtn">${fit ? 'Re-check fit' : 'Check my fit'}</button>
      ${fit ? `<span class="pill ${fit.score >= 70 ? 'good' : fit.score >= 45 ? 'warn' : 'bad'}">${fit.score}/100</span>` : ''}</div>
    ${fit ? `
      <p><b>${esc(fit.verdict)}</b></p>
      ${fit.domain ? `<p class="small">🏷️ <b>Domain:</b> ${esc(fit.domain)}</p>` : ''}
      <div class="section-title">Lead with</div><ul>${fit.emphasize.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      <div class="section-title">Requirements</div>
      ${fit.requirements.map(r => `<div class="req"><span class="pill ${lvl[r.level]}">${r.level}</span><div>${esc(r.requirement)}<div class="muted small">${esc(r.note)}</div></div></div>`).join('')}
      <div class="section-title">Your edge</div><ul>${fit.unique_strengths.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      <div class="section-title">Gaps</div><ul>${fit.gaps.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    <div class="section-title">Details</div>
    <form id="jobForm" class="grid2">
      <label>Company<input class="input" name="company" value="${esc(job.company)}"></label>
      <label>Role<input class="input" name="role" value="${esc(job.role)}"></label>
      <label>Job URL<input class="input" name="url" value="${esc(job.url)}"></label>
      <label>Location<input class="input" name="location" value="${esc(job.location)}"></label>
      <label>Which version got a response?<select class="input" name="response_variant">${[['', 'No response yet'], ['A', 'Version A'], ['B', 'Version B'], ['both', 'Both'], ['none', 'Neither (closed)']].map(([val, l]) => `<option value="${val}" ${val === (job.response_variant || '') ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label>Priority<select class="input" name="priority">${[[1, 'High'], [2, 'Normal'], [3, 'Low']].map(([v, l]) => `<option value="${v}" ${v === job.priority ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label>LinkedIn company ID <span class="small">(from the company page's URL when you filter its people)</span><input class="input" name="company_linkedin_id" value="${esc(job.company_linkedin_id)}"></label>
      <label style="grid-column:1/-1">Notes<textarea class="input" name="notes" rows="3">${esc(job.notes)}</textarea></label>
      <label style="grid-column:1/-1">Job description<textarea class="input" name="jd" rows="12">${esc(job.jd)}</textarea></label>
    </form>
    <div class="row gap"><button class="btn primary" id="saveJob">Save</button><button class="btn" id="delJob">Delete role</button></div>`;

  $('#fitBtn').onclick = e => busy(e.target, 'Checking… (~20s)', async () => {
    await api(`/api/jobs/${job.id}/fit`, { method: 'POST' });
    await openJob(job.id, 'overview');
    loadBoard();
  });
  $('#saveJob').onclick = async () => {
    const f = Object.fromEntries(new FormData($('#jobForm')));
    f.priority = +f.priority;
    await api(`/api/jobs/${job.id}`, { method: 'PATCH', body: f });
    toast('Saved');
    await openJob(job.id, 'overview');
    loadBoard();
  };
  $('#delJob').onclick = async () => {
    if (!confirm(`Delete ${job.company} · ${job.role}?`)) return;
    await api(`/api/jobs/${job.id}`, { method: 'DELETE' });
    closeDrawer();
    loadBoard();
  };
}

function renderLogTab() {
  const { log } = state.openJob;
  $('#drawerBody').innerHTML = log.length
    ? log.map(l => `<div class="person"><div class="row between"><b>${esc(l.kind)}${l.name ? ` · ${esc(l.name)}` : ''}</b><span class="muted small">${esc(l.created_at)}</span></div><div class="small" style="white-space:pre-wrap">${esc(l.body)}</div></div>`).join('')
    : '<p class="muted">Nothing logged yet. When you mark a message as sent, it shows up here.</p>';
}

// ---------- add role ----------
let addMode = 'paste';
function openAdd() {
  $('#addForm').reset();
  $('#addMsg').textContent = '';
  $('#addDialog').showModal();
  $(`[data-mode-panel="${addMode}"] textarea, [data-mode-panel="${addMode}"] input`).focus();
}
window.openAdd = openAdd;
$('#addRoleBtn').onclick = openAdd;
$$('#addModeTabs button').forEach(b => b.onclick = () => {
  addMode = b.dataset.mode;
  $$('#addModeTabs button').forEach(x => x.classList.toggle('active', x === b));
  $$('[data-mode-panel]').forEach(p => p.classList.toggle('hidden', p.dataset.modePanel !== addMode));
});
$('#addForm').onsubmit = async e => {
  if (e.submitter?.value !== 'ok') return;
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  const btn = $('#addSubmit');
  try {
    const { id } = await busy(btn, addMode === 'paste' ? 'Reading posting…' : 'Adding…', () =>
      addMode === 'paste'
        ? api('/api/jobs/from-paste', { method: 'POST', body: { text: f.text, url: f.url } })
        : api('/api/jobs', { method: 'POST', body: { company: f.company, role: f.role, url: f.murl, location: f.location, jd: f.jd } }));
    if (f.high) await api(`/api/jobs/${id}`, { method: 'PATCH', body: { priority: 1 } });
    $('#addDialog').close();
    await loadBoard();
    openJob(id, 'resume');
  } catch (err) { $('#addMsg').textContent = err.message; }
};

// ---------- people view ----------
async function loadPeople() {
  const list = await api(`/api/people?q=${encodeURIComponent($('#peopleSearch').value)}`);
  $('#peopleCount').textContent = list.length;
  const src = { connections: '1st-degree', referral_sheet: 'Referral sheet', manual: 'Added' };
  $('#peopleRows').innerHTML = list.map(p => `
    <tr><td>${esc(p.name)}</td><td>${esc(p.company)}</td><td class="small">${esc(p.title)}</td>
    <td><span class="pill ${p.source === 'referral_sheet' ? 'good' : ''}">${src[p.source] || p.source}</span></td>
    <td>${p.linkedin_url ? `<a href="${esc(p.linkedin_url)}" target="_blank" rel="noopener">↗</a>` : ''}</td></tr>`).join('');
}
let peopleT;
$('#peopleSearch').oninput = () => { clearTimeout(peopleT); peopleT = setTimeout(loadPeople, 200); };
$$('[data-import]').forEach(inp => inp.onchange = async () => {
  const fd = new FormData();
  fd.append('file', inp.files[0]);
  $('#importMsg').textContent = 'Importing…';
  try {
    const r = await api(`/api/import/${inp.dataset.import}`, { method: 'POST', body: fd });
    $('#importMsg').textContent = `✓ ${r.added} added, ${r.updated} updated`;
    await loadMeta();
    loadPeople();
    loadBoard();
  } catch (e) { $('#importMsg').textContent = e.message; }
  inp.value = '';
});

// ---------- me / profile ----------
const ME_FIELDS = [
  ['name', 'Name'], ['headline', 'Headline (one line)'], ['location', 'Location'], ['linkedin_url', 'LinkedIn URL'],
  ['school', 'School'], ['grad_year', 'Grad year'], ['past_employers', 'Past employers (comma separated)'],
  ['programs', 'Clubs / programs / bootcamps (comma separated)'], ['hometown', 'Hometown'],
  ['calendly_url', 'Calendly link (offered in messages)'],
  ['target_roles', 'Target roles (comma separated)'], ['avoid_roles', "Roles I don't want (comma separated)"], ['connection_note_limit', 'Connection note limit (200 free, 300 Premium)'],
];
async function loadProfile() {
  await loadMeta();
  const me = state.meta.me;
  $('#meForm').innerHTML = ME_FIELDS.map(([k, l]) =>
    `<label>${l}<input class="input" name="${k}" value="${esc(Array.isArray(me[k]) ? me[k].join(', ') : me[k])}"></label>`).join('');
  const files = state.meta.profile_files;
  $('#profileFileTabs').innerHTML = Object.entries(files).map(([name, f]) =>
    `<button class="chip ${name === state.profileFile ? 'active' : ''}" data-file="${name}">${f.filled ? '✓' : '○'} ${name}</button>`).join('');
  $$('#profileFileTabs .chip').forEach(c => c.onclick = () => { state.profileFile = c.dataset.file; loadProfile(); });
  $('#profileFileDesc').textContent = files[state.profileFile].description;
  const f = await api(`/api/profile/${state.profileFile}`);
  $('#profileText').value = f.text;
  $('#profileMsg').textContent = f.filled ? '' : 'This is the blank template. Replace it with your real content and Save.';
  const rs = await api('/api/role-searches');
  $('#roleSearches').innerHTML = rs.length
    ? rs.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)} ↗</a>`).join('')
    : '<span class="muted">Add target roles above to get search links.</span>';
}
$('#saveMe').onclick = async () => {
  const f = Object.fromEntries(new FormData($('#meForm')));
  for (const k of ['past_employers', 'programs', 'target_roles', 'avoid_roles']) f[k] = f[k].split(',').map(s => s.trim()).filter(Boolean);
  f.connection_note_limit = +f.connection_note_limit || 200;
  f.weights = state.meta.me.weights;
  await api('/api/me', { method: 'PUT', body: f });
  $('#meMsg').textContent = 'Saved ✓';
  loadProfile();
};
$('#saveProfileFile').onclick = async () => {
  await api(`/api/profile/${state.profileFile}`, { method: 'PUT', body: { text: $('#profileText').value } });
  toast('Saved');
  loadProfile();
};

// ---------- keyboard ----------
document.addEventListener('keydown', e => {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
  if (e.key === 'Escape' && state.openJob) closeDrawer();
  if (typing || e.metaKey || e.ctrlKey) return;
  if (e.key === 'n') { e.preventDefault(); openAdd(); }
  if (e.key === '/') { e.preventDefault(); showView('board'); $('#search').focus(); }
});

// ---------- boot ----------
(async () => {
  await loadMeta();
  await loadBoard();
  const params = new URLSearchParams(location.search);
  if (params.get('job')) openJob(+params.get('job'), params.get('tab') || undefined);
})();
