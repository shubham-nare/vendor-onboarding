/* Vendors (GET /api/v1/vendors): one row per legal entity, with filters kept in the address bar. */

const VTONE = { active: 'text-emerald-700', onboarding: 'text-amber-700', rejected: 'text-rose-700', on_record: 'text-slate-600', inactive: 'text-slate-500' };
const PTONE = { eligible: ['Eligible', 'text-emerald-700'], blocked: ['Blocked', 'text-rose-700'], not_yet: ['Not yet', 'text-slate-500'] };

App.views['/vendors'] = {
  title: 'Vendors',
  async render(view) {
    const params = new URLSearchParams(location.search);
    const f = Object.fromEntries(['q', 'status', 'risk', 'pay', 'inv', 'sort'].map(k => [k, params.get(k) || '']));
    const d = await api('/vendors?' + new URLSearchParams(f));
    const filtered = Object.values(f).some(Boolean);
    const sel = (name, label, opts) => `<label class="flex flex-col gap-1 text-slate-500">${label}<select name="${name}" class="rounded-lg border px-2 py-2 text-slate-800">${opts.map(([k, l]) => `<option value="${k}"${k === f[name] ? ' selected' : ''}>${l}</option>`).join('')}</select></label>`;
    const money = n => n ? inr(n) : '—';
    const rows = d.vendors.map(v => {
      const risk = !d.full ? '' : `<td class="px-2 py-3" data-label="Risk">${v.risk.open ? `<span class="tag dot ${v.risk.fraud ? 'text-rose-700' : 'text-amber-700'}">${v.risk.open} open</span>` : v.risk.linked ? '<span class="tag text-amber-700">linked</span>' : '<span class="text-slate-400">none</span>'}</td>`;
      return `<tr class="group hover:bg-slate-50/80 cursor-pointer" data-href="/vendors/${esc(v.id)}">
        <td class="pl-5 pr-2 py-3 min-w-[15rem]"><div class="flex items-center gap-3">${monogram(v.name)}<div class="min-w-0">
          <a href="/vendors/${esc(v.id)}" class="block font-medium text-slate-900 group-hover:text-indigo-700">${esc(v.name)}</a>
          <div class="mt-0.5 text-[11.5px] text-slate-500"><span class="mono">${esc(v.id)}</span>${v.erp_id ? ` · <span class="mono">${esc(v.erp_id)}</span>` : ''}</div></div></div></td>
        ${d.full ? `<td class="px-2 py-3 mono text-[11.5px] text-slate-600" data-label="PAN · GSTIN">${esc(v.pan || '—')}${v.gstins.map(g => `<div>${esc(g)}</div>`).join('')}</td>` : ''}
        <td class="px-2 py-3" data-label="Onboarding"><span class="tag dot ${VTONE[v.status] || 'text-slate-500'}">${esc(v.status_label)}</span>${v.latest_application ? `<div class="text-[11.5px] text-slate-500 mono mt-0.5">${esc(v.latest_application)}</div>` : ''}</td>
        ${risk}
        <td class="px-2 py-3" data-label="Payment"><span class="${PTONE[v.payment][1]} font-medium">${PTONE[v.payment][0]}</span></td>
        <td class="px-2 py-3 text-right tabular-nums" data-label="Active invoices">${v.active_invoices || '—'}</td>
        <td class="px-2 py-3 text-right tabular-nums" data-label="Awaiting review">${money(v.awaiting_review)}</td>
        <td class="px-2 py-3 text-right tabular-nums" data-label="Approved, unpaid">${money(v.approved_unpaid)}</td>
        <td class="px-2 py-3 text-[12px] text-slate-500 whitespace-nowrap" data-label="Last activity">${esc(v.last_activity.label || '—')}</td>
        <td class="pr-5 pl-2 py-3 text-[12.5px] font-medium text-slate-800" data-label="Next best action">${esc(v.next || '—')}</td></tr>`;
    }).join('');
    view.innerHTML = `<div class="space-y-5"><div><h1>Vendors</h1>
      ${d.full ? '' : '<p class="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[12.5px] text-amber-900">Only the vendors you asked for.</p>'}</div>
      <form id="v-filter" class="flex flex-wrap items-end gap-2 text-[12.5px]">
        <input name="q" value="${esc(f.q)}" type="search" placeholder="Name, VND- or V- number" aria-label="Search vendors" class="w-full sm:w-64 rounded-lg border px-3 py-2">
        ${sel('status', 'Onboarding', [['', 'Any'], ['onboarding', 'Onboarding'], ['active', 'Active'], ['rejected', 'Rejected'], ['on_record', 'On record']])}
        ${d.full ? sel('risk', 'Risk', [['', 'Any'], ['flagged', 'Open flags']]) : ''}
        ${sel('pay', 'Payment', [['', 'Any'], ['eligible', 'Eligible'], ['blocked', 'Blocked'], ['not_yet', 'Not yet']])}
        ${sel('inv', 'Invoices', [['', 'Any'], ['needs_review', 'Need review'], ['unpaid', 'Approved, unpaid']])}
        ${sel('sort', 'Sort', [['', 'Needs action first'], ['activity', 'Last activity'], ['awaiting', 'Awaiting review (₹)'], ['unpaid', 'Approved, unpaid (₹)']])}
        <button class="rounded-lg bg-indigo-600 text-white font-semibold px-4 py-2 hover:bg-indigo-700">Apply</button>
        ${filtered ? '<a href="/vendors" class="px-2 py-2 text-indigo-700 hover:underline">Clear</a>' : ''}</form>
      <section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]">
        <thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">Vendor</th>${d.full ? '<th class="px-2">PAN · GSTIN</th>' : ''}<th class="px-2">Onboarding</th>${d.full ? '<th class="px-2">Risk</th>' : ''}<th class="px-2">Payment</th><th class="px-2 text-right">Active invoices</th><th class="px-2 text-right">Awaiting review</th><th class="px-2 text-right">Approved, unpaid</th><th class="px-2">Last activity</th><th class="pr-5 pl-2">Next best action</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>`
        : emptyState(filtered ? 'No vendor matches' : 'No vendors yet', filtered ? 'Try other filters.' : 'Vendors appear after their first check, and existing vendor-master records are included.')}</section></div>`;
    qs('#v-filter', view).addEventListener('submit', e => {
      e.preventDefault();
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
      navigate('/vendors' + (p.toString() ? '?' + p : ''));
    });
  },
};
