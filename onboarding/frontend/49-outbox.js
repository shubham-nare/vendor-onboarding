/* Outbox (GET /api/v1/outbox): what we told vendors, notes to requesters, and the Contact us inbox. */

const KIND_TAG = { reminder: '<span class="tag text-amber-700">reminder</span>', escalation: '<span class="tag text-rose-700">second reminder</span>' };
const EMAIL_TONE = { sent: 'text-emerald-700', failed: 'text-rose-700' };

App.views['/outbox'] = {
  title: 'Outbox',
  async render(view) {
    const d = await api('/outbox');
    const inbox = d.inbox.map(m => `<li class="px-4 sm:px-5 py-3 text-[13.5px]">
      <div class="flex flex-wrap items-baseline gap-x-2"><b>${esc(m.name)}</b>${m.company ? `<span class="text-slate-500">· ${esc(m.company)}</span>` : ''}
        <a class="text-indigo-700 hover:underline" href="mailto:${esc(m.email)}">${esc(m.email)}</a>${m.topic ? `<span class="tag text-slate-600">${esc(m.topic)}</span>` : ''}
        <span class="ml-auto text-[12px] text-slate-500">${esc(m.received.label)}</span></div>
      <p class="mt-1 text-slate-700 whitespace-pre-wrap">${esc(m.body)}</p></li>`).join('');
    const cards = d.messages.map(m => `<div class="bg-white rounded-xl border p-4 sm:p-5">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span class="mono text-slate-500">${esc(m.ref)}</span><a href="/runs/${m.run_id}" class="text-indigo-700 underline">${esc(m.vendor)}</a>
        <span class="text-slate-400">${esc(m.sent.label)}</span>${m.kind === 'note' ? `<span class="tag text-rose-700">to ${esc(m.to)}</span>` : (KIND_TAG[m.kind] || '')}
        <span class="ml-auto tag ${m.state === 'sent' ? 'text-emerald-700' : 'text-amber-700'}">${esc(m.state)}</span>
        ${m.email ? `<span class="tag ${EMAIL_TONE[m.email.status] || 'text-slate-500'}">${esc(m.email.label)}${m.email.to ? ' to ' + esc(m.email.to) : ''}</span>` : ''}</div>
      <div class="mono text-[11.5px] text-slate-500 mt-3 pt-3 border-t border-dashed border-slate-300">Subject: ${esc(m.subject)}</div>
      <pre class="mt-1 whitespace-pre-wrap break-words font-display text-[16px] leading-relaxed text-slate-800">${esc(m.body)}</pre></div>`).join('');
    view.innerHTML = `<div><div class="kicker">Correspondence</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Vendor outbox</h1>
      ${inbox ? `<section class="mt-6 bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-5 py-3.5 border-b border-slate-100"><h2 class="text-[16px]">From the Contact us form <span class="text-slate-400 font-normal">${d.inbox.length}</span></h2></div>
        <ul class="divide-y divide-slate-100">${inbox}</ul></section>` : ''}
      <div class="mt-6 grid xl:grid-cols-2 gap-3 items-start">${cards || '<p class="text-sm text-slate-500">No messages yet.</p>'}</div></div>`;
  },
};
