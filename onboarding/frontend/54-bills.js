/* Bills (GET /api/v1/bills): from active vendors, and sent with a registration. */

const BILL_TONE = { approved: 'text-emerald-700', rejected: 'text-rose-600', vendor_fix: 'text-amber-700', for_review: 'text-amber-700',
                    awaiting_confirmation: 'text-amber-700', ready_for_approval: 'text-emerald-700', checking: 'text-slate-500', failed: 'text-rose-600' };

App.views['/bills'] = {
  title: 'Bills',
  async render(view) {
    const d = await api('/bills');
    const conf = b => b.confirmation === 'confirmed' ? ' ✓' : b.confirmation === 'denied' ? ' <span class="text-rose-600">denies</span>' : '';
    const rows = d.bills.map(b => `<tr class="hover:bg-slate-50 cursor-pointer" data-href="/bills/${b.id}">
      <td class="pl-5 pr-2 py-3 whitespace-nowrap"><a href="/bills/${b.id}" class="mono text-[12.5px] hover:text-indigo-700">${esc(b.ref)}</a></td>
      <td class="px-2 py-3 font-medium" data-label="Vendor"><span class="inline-flex items-center gap-2.5">${monogram(b.vendor.name, 'h-7 w-7 text-[10.5px]')}${esc(b.vendor.name)}</span> <span class="mono text-[11px] text-slate-500 font-normal">${esc(b.vendor.id)}</span>${b.fraud ? ' <span class="tag text-indigo-600 !text-[9px]">fraud class</span>' : ''}</td>
      <td class="px-2 py-3 mono text-[12px]" data-label="Invoice">${esc(b.invoice_number || 'being read…')}</td>
      <td class="px-2 py-3 text-right whitespace-nowrap" data-label="Amount">${inr(b.amount)}</td>
      <td class="inline-sm px-2 py-3"><span class="tag ${BILL_TONE[b.status] || ''}">${esc(b.status_label)}</span></td>
      <td class="inline-sm px-2 py-3">${tierChip(b.risk)}</td>
      <td class="pr-5 pl-2 py-3 text-[13px] text-slate-600" data-label="Asked for by">${esc(b.asked_for_by || '')}${conf(b)}</td></tr>`).join('');
    const regs = d.with_registration.map(r => `<li><a href="/runs/${r.run_id || ''}#bill" class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 sm:px-5 py-3 hover:bg-slate-50 text-sm">
      ${monogram(r.name, 'h-8 w-8 text-[11px]')}<span class="mono text-[12px] text-slate-500 w-20">${esc(r.ref)}</span>
      <span class="flex-1 min-w-[12rem] font-medium">${esc(r.name)} <span class="mono text-[11.5px] text-slate-500 font-normal">${esc(r.invoice_number || '')}</span></span>
      <span class="font-semibold tabular-nums">${inr(r.amount)}</span><span class="text-xs text-slate-500">${esc(r.asked_for_by || '')} · ${esc(r.confirmation)}</span></a></li>`).join('');
    view.innerHTML = `<div><div class="kicker">Accounts payable</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">${d.full ? 'Bills' : 'Bills that name you'}</h1>
      <section class="mt-6 bg-white rounded-xl border"><div class="px-4 sm:px-5 py-4 border-b border-slate-200"><h2 class="text-xl">From active vendors</h2></div>
        ${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-sm"><thead class="text-left text-slate-500 bg-slate-50 border-b border-slate-200"><tr><th class="pl-5 pr-2 py-2.5 font-medium">Ref</th><th class="px-2 font-medium">Vendor</th><th class="px-2 font-medium">Invoice</th><th class="px-2 font-medium text-right">Amount</th><th class="px-2 font-medium">Status</th><th class="px-2 font-medium">Risk</th><th class="pr-5 pl-2 font-medium">Asked for by</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>` : emptyState('No bills from active vendors yet', 'An active vendor sends them from the supplier portal; each is checked, then confirmed and approved here.')}</section>
      <section class="mt-6 bg-white rounded-xl border"><div class="px-4 sm:px-5 py-4 border-b border-slate-200"><h2 class="text-xl">Sent with a registration</h2><p class="text-xs text-slate-500 mt-1">Vendors with no invite who registered with a bill for work already done. They're checked inside the registration run.</p></div>
        ${regs ? `<ul class="divide-y divide-slate-100">${regs}</ul>` : emptyState('None yet', 'Vendors who did work before registering send their bill with the registration.')}</section></div>`;
  },
};
