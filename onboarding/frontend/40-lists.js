/* Applications (GET /api/v1/applications) and Review (GET /api/v1/review). */

const emptyState = (title, text) => `<div class="px-5 py-10 text-center">
  <span class="mx-auto h-11 w-11 rounded-full bg-slate-100 text-slate-500 grid place-items-center">${icon('check', 'h-5 w-5')}</span>
  <p class="mt-3 text-[14px] font-medium text-slate-800">${esc(title)}</p><p class="mt-1 text-[12.5px] text-slate-500 max-w-sm mx-auto">${esc(text)}</p></div>`;

// a table row that opens a link when clicked anywhere (links inside it still work on their own)
document.addEventListener('click', e => {
  const row = e.target.closest('tr[data-href]');
  if (!row || e.target.closest('a, button, input, select')) return;
  navigate(row.dataset.href);
});

const APP_STATUSES = [['', 'Any status'], ['PENDING_REVIEW', 'Internal review'], ['PENDING_VENDOR', 'Vendor to fix'], ['APPROVED', 'Approved'], ['ACTIVE', 'Active'], ['PREQUALIFIED', 'Pre-qualified'], ['REJECTED', 'Rejected']];

App.views['/applications'] = {
  title: 'Applications',
  async render(view) {
    const params = new URLSearchParams(location.search), status = params.get('status') || '', q = params.get('q') || '';
    const d = await api('/applications?' + new URLSearchParams({ status, q }));
    paintCounts(d.counts);
    const rows = d.applications.map(x => `<tr class="group hover:bg-slate-50/80 ${x.run_id ? 'cursor-pointer' : ''} ${x.waiting ? 'bg-rose-50/40' : ''}"${x.run_id ? ` data-href="/runs/${x.run_id}"` : ''}>
      <td class="pl-5 pr-2 py-3">${x.run_id ? `<a href="/runs/${x.run_id}" class="mono font-medium group-hover:text-indigo-700">${esc(x.ref)}</a>` : `<span class="mono font-medium">${esc(x.ref)}</span>`}
        ${x.waiting ? '<span class="ml-1 inline-flex items-center rounded-full bg-[#FF3B30] text-white text-[10.5px] font-semibold px-2 py-0.5 align-middle">Waiting for you</span>' : ''}
        <div class="text-[11.5px] text-slate-500">${esc(x.name)}</div></td>
      <td class="px-2 py-3" data-label="Vendor">${x.vendor ? `<a class="hover:text-indigo-700" href="/vendors/${esc(x.vendor.id)}">${esc(x.vendor.name)}</a><div class="text-[11.5px] text-slate-500 mono">${esc(x.vendor.id)}</div>` : '—'}</td>
      <td class="px-2 py-3" data-label="Status">${statusBadge(x.status)}</td>
      <td class="px-2 py-3" data-label="Risk">${x.risk ? tierChip(x.risk) : '—'}</td>
      <td class="px-2 py-3 text-slate-600" data-label="Came in through">${esc(x.came_in)}</td>
      <td class="pr-5 pl-2 py-3 text-slate-500 whitespace-nowrap" data-label="Submitted">${esc(x.submitted.label)}</td></tr>`).join('');
    view.innerHTML = `<div class="space-y-5">
      <div class="flex flex-wrap items-end justify-between gap-4"><h1>Applications</h1>
        <form id="app-filter" class="flex gap-2 w-full sm:w-auto">
          <select name="status" class="rounded-lg border px-2 py-2 text-[13px]" aria-label="Status">${APP_STATUSES.map(([k, l]) => `<option value="${k}"${k === status ? ' selected' : ''}>${l}</option>`).join('')}</select>
          <input name="q" value="${esc(q)}" type="search" placeholder="VOB-number, name or GSTIN" aria-label="Search applications" class="w-full sm:w-64 rounded-lg border px-3 py-2 text-[13px]">
          <button class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-[13px] font-medium hover:bg-slate-50">Filter</button>
        </form></div>
      <section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]">
        <thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">Application</th><th class="px-2">Vendor</th><th class="px-2">Status</th><th class="px-2">Risk</th><th class="px-2">Came in through</th><th class="pr-5 pl-2">Submitted</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>`
        : emptyState(status || q ? 'No applications match' : 'No applications yet', status || q ? 'Try another filter.' : 'Applications arrive through invites and the supplier portal.')}</section>
    </div>`;
    qs('#app-filter', view).addEventListener('submit', e => {
      e.preventDefault();
      const f = new FormData(e.target), p = new URLSearchParams();
      if (f.get('status')) p.set('status', f.get('status'));
      if (f.get('q')) p.set('q', f.get('q'));
      navigate('/applications' + (p.toString() ? '?' + p : ''));
    });
  },
};

const reviewRow = (t, full) => `<li><a href="${esc(t.href)}" class="group flex flex-wrap items-center gap-3 px-4 sm:px-5 py-3 hover:bg-slate-50">
  ${monogram(t.name)}
  <span class="flex-1 min-w-[14rem]"><span class="block text-[14px] font-medium group-hover:text-indigo-700">${esc(t.name)}</span>
    <span class="block text-[12px] text-slate-500"><span class="mono">${esc(t.ref)}</span>${t.detail ? ' · ' + esc(t.detail) : ''}${t.amount ? ' · ' + inr(t.amount) : ''}${t.waiting ? ' · ' + esc(t.waiting) : ''}</span></span>
  ${['BILL', 'CHANGE'].includes(t.status) ? '' : statusBadge(t.status)}${full ? tierChip(t.risk) : ''}
  <span class="hidden sm:inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white group-hover:bg-indigo-700">${esc(t.verb)} ${icon('chev', 'h-3.5 w-3.5')}</span></a></li>`;

function changeItem(c) {
  const req = Object.entries(c.requested).map(([k, v]) => `<span class="mr-3"><span class="text-slate-500">${esc(k)}:</span> <span class="mono">${esc(v)}</span></span>`).join('');
  return `<li class="px-4 sm:px-5 py-3.5" data-change="${c.id}">
    <div class="flex flex-wrap items-center gap-2"><span class="tag ${c.kind === 'bank_account' ? 'text-rose-700' : 'text-slate-600'}">${c.kind === 'bank_account' ? 'bank account change' : 'contact change'}</span>
      ${c.vendor_id ? `<a class="font-medium hover:text-indigo-700" href="/vendors/${esc(c.vendor_id)}">${esc(c.name)}</a>` : `<span class="font-medium">${esc(c.name)}</span>`}
      <span class="text-[12px] text-slate-500">${esc(c.created.label)}</span></div>
    <div class="mt-1 text-[13px] text-slate-700">${req}${c.reason ? `<div class="text-slate-500">Reason given: ${esc(c.reason)}</div>` : ''}
      ${c.document ? `<a class="text-indigo-700 hover:underline" target="_blank" rel="noopener" href="/files/${esc(c.document.sha256)}">${esc(c.document.name)}</a>` : ''}</div>
    ${c.mine ? `<form class="mt-2 flex flex-wrap gap-2" data-decide="${c.id}">
        <input name="note" required minlength="5" placeholder="How you checked it" class="flex-1 min-w-[14rem] rounded-md border px-3 py-1.5 text-[13px]">
        <button name="decision" value="approve" class="rounded-md bg-indigo-600 text-white px-3 py-1.5 text-[13px] font-semibold hover:bg-indigo-700">Approve</button>
        <button name="decision" value="reject" class="rounded-md border border-rose-300 bg-white text-rose-700 px-3 py-1.5 text-[13px] font-semibold hover:bg-rose-50">Reject</button>
        <p class="w-full text-[12.5px] text-rose-700" data-error hidden></p></form>`
      : '<p class="mt-1.5 text-[12px] text-slate-500">Bank-account changes are decided by the Finance controller.</p>'}</li>`;
}

App.views['/review'] = {
  title: 'Review',
  async render(view) {
    const d = await api('/review');
    paintCounts(d.counts);
    const list = (items, none) => items.length ? `<ul class="divide-y divide-slate-100">${items.map(t => reviewRow(t, d.full)).join('')}</ul>` : `<p class="px-5 py-4 text-[13px] text-slate-500">${none}</p>`;
    view.innerHTML = `<div class="space-y-6"><h1>Review</h1>
      ${d.full && d.changes.length ? `<section id="changes" class="bg-white border rounded-xl overflow-hidden">
        <div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Change requests <span class="text-slate-400 font-normal">${d.changes.length}</span></h2>
          <p class="text-[12.5px] text-slate-500 mt-0.5">Approve a new bank account only after checking it independently, for example by calling a number already on record.</p></div>
        <ul class="divide-y divide-slate-100">${d.changes.map(changeItem).join('')}</ul></section>` : ''}
      <section class="bg-white border rounded-xl overflow-hidden">
        <div class="px-4 sm:px-5 py-4 border-b border-slate-100 flex items-baseline justify-between gap-3"><h2 class="text-[16px]">Invoices <span class="text-slate-400 font-normal">${d.invoices.length}</span></h2>
          <a href="/invoices" data-optional class="text-[13px] text-indigo-700 hover:underline">All invoices ›</a></div>
        ${list(d.invoices, 'No invoices need you right now.')}</section>
      <section class="bg-white border rounded-xl overflow-hidden">
        <div class="px-4 sm:px-5 py-4 border-b border-slate-100 flex items-baseline justify-between gap-3"><h2 class="text-[16px]">Vendor decisions <span class="text-slate-400 font-normal">${d.apps.length}</span></h2>
          <a href="/applications" class="text-[13px] text-indigo-700 hover:underline">All applications ›</a></div>
        ${list(d.apps, 'No vendor decisions need you right now.')}</section></div>`;
    qsa('form[data-decide]', view).forEach(f => f.addEventListener('submit', async e => {
      e.preventDefault();
      const err = qs('[data-error]', f), note = f.note.value.trim();
      qsa('button', f).forEach(b => { b.disabled = true; });
      try {
        await api(`/change-requests/${f.dataset.decide}/decision`, { method: 'POST', body: { decision: e.submitter.value, note } });
        await App.views['/review'].render(view);
      } catch (x) {
        err.textContent = x.message; err.hidden = false;
        qsa('button', f).forEach(b => { b.disabled = false; });
      }
    }));
    if (location.hash === '#changes') qs('#changes', view)?.scrollIntoView();
  },
};
