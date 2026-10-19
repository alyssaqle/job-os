// Service worker: remembers which tracked job each tab is on, and turns content-script
// signals ("applied!", "sent a request") into API calls. Tells the side panel what happened.
'use strict';

const API = 'http://localhost:8000';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

async function post(path, body) {
  const res = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// Remember the last tracked job seen per tab, plus the last one seen anywhere. Clicking "Apply" on
// LinkedIn often opens the company's site in a new tab, so the confirmation page won't match by URL.
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== 'complete' || !tab.url?.startsWith('http')) return;
  try {
    const { job } = await post('/api/page/job', { url: tab.url });
    if (job) await chrome.storage.session.set({ [`tab:${tabId}`]: job.id, lastJob: { id: job.id, at: Date.now() } });
  } catch { /* server not running */ }
});

function notify(text, extra = {}) {
  chrome.runtime.sendMessage({ type: 'tracked', text, ...extra }).catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  (async () => {
    if (msg.type === 'applied') {
      const tabId = sender.tab?.id;
      const store = await chrome.storage.session.get([`tab:${tabId}`, 'lastJob']);
      let jobId = store[`tab:${tabId}`];
      if (!jobId && store.lastJob && Date.now() - store.lastJob.at < 45 * 60 * 1000) jobId = store.lastJob.id;
      try {
        const r = await post('/api/track/applied', { job_id: jobId || null, url: msg.url });
        notify(`✓ Marked applied: ${r.company} · ${r.role}. Next: reach out.`, { jobId: r.id, kind: 'applied' });
      } catch {
        notify('Looks like you just applied, but I couldn\'t tell to which job. Tap "I applied" on it.');
      }
    }
    if (msg.type === 'outreach') {
      try {
        const r = await post('/api/track/outreach', { linkedin_url: msg.linkedin_url, kind: msg.kind, message: msg.message || '' });
        if (r.ok) notify(`✓ Logged ${msg.kind === 'requested' ? 'connection request to' : 'message to'} ${r.person}`, { kind: msg.kind });
      } catch { /* person not captured yet; the panel's manual button still works */ }
    }
    if (msg.type === 'remember-job') {
      await chrome.storage.session.set({ [`tab:${msg.tabId}`]: msg.jobId, lastJob: { id: msg.jobId, at: Date.now() } });
    }
  })();
});
