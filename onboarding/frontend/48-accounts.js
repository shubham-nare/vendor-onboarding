/* Supplier portal accounts (GET /api/v1/supplier-accounts): reviewers and Finance only. */

App.views['/supplier-accounts'] = {
  title: 'Accounts',
  async render(view) {
    const d = await api('/supplier-accounts');
    const card = a => `<section class="bg-white rounded-xl border p-4 sm:p-5">
      <div class="flex flex-wrap items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-3 min-w-0">${monogram(a.company, 'h-10 w-10 text-[13px]')}
        <div class="min-w-0"><div class="font-semibold text-[15.5px]">${esc(a.company)}</div><div class="text-xs text-slate-500 mt-0.5 break-all">${esc(a.contact)} · <a class="hover:underline" href="mailto:${esc(a.email)}">${esc(a.email)}</a> · account since ${esc(a.since.label)}</div></div></div></div>
        ${a.vendor_id ? `<div class="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5"><span class="text-[11.5px] font-medium text-emerald-700">Vendor ID</span><span class="mono text-[14px] font-medium text-emerald-900">${esc(a.vendor_id)}</span></div>` : ''}</div>
      <div class="mt-3 flex flex-wrap gap-2 text-sm">
        ${a.pending_invites.map(n => `<span class="tag text-violet-600">invited by ${esc(n)} · not submitted</span>`).join('')}
        ${a.registrations.map(r => `<${r.run_id ? `a href="/runs/${r.run_id}"` : 'span'} class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/60 px-2.5 py-1.5 hover:border-indigo-300 hover:bg-white"><span class="mono text-[12px]">${esc(r.ref)}</span>${statusBadge(r.status)}<span class="text-xs text-slate-500">${esc(r.came_in)}</span></${r.run_id ? 'a' : 'span'}>`).join('')}
        ${a.registrations.length || a.pending_invites.length ? '' : '<span class="text-xs text-slate-500">Account created; no registration yet.</span>'}</div>
      ${a.bills.length ? `<div class="mt-3 text-xs text-slate-600">Bills: ${a.bills.map(b => `<a href="/bills/${b.id}" class="underline mr-2">${esc(b.ref)} ${inr(b.amount)} · ${esc(b.status)}</a>`).join('')}</div>` : ''}</section>`;
    view.innerHTML = `<div><div class="kicker">Supplier portal accounts</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Accounts</h1>
      <div class="mt-6 space-y-3">${d.accounts.length ? d.accounts.map(card).join('') : `<section class="bg-white rounded-xl border">${emptyState('No vendor accounts yet', "Vendors create one from the home page (I'm a vendor or supplier).")}</section>`}</div></div>`;
  },
};
