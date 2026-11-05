/* Orders (GET /api/v1/purchase-orders): red when an invoice against the order doesn't match it. */

App.views['/purchase-orders'] = {
  title: 'Orders',
  async render(view) {
    const q = new URLSearchParams(location.search).get('q') || '';
    const d = await api('/purchase-orders?' + new URLSearchParams({ q }));
    const dot = (c, label) => `<span><span class="inline-block h-3 w-3 rounded-full ${c} align-middle mr-1.5"></span>${label}</span>`;
    const rows = d.orders.map(o => `<tr class="group cursor-pointer row-${o.tone}" data-href="/purchase-orders/${o.id}">
      <td class="pl-5 pr-2 py-3 whitespace-nowrap"><a href="/purchase-orders/${o.id}" class="mono text-[12.5px] font-medium ${o.tone === 'red' ? 'text-rose-800' : ''}">${esc(o.number)}</a>
        <div class="text-[11.5px] text-slate-500">${esc(o.cost_centre)} · ${esc(o.status)}</div>
        ${o.issues.length ? `<div class="mt-1 text-[11.5px] font-semibold text-rose-700">${o.issues.map(esc).join(' · ')}</div>` : ''}</td>
      <td class="px-2 py-3" data-label="Vendor">${esc(o.vendor.name)}<div class="text-[11.5px] text-slate-500 mono">${esc(o.vendor.gstin)}</div></td>
      <td class="px-2 py-3 text-[13px]" data-label="Requested by">${esc(o.requested_by || '—')}</td>
      <td class="px-2 py-3 text-right tabular-nums" data-label="Order value">${inr(o.total)}</td>
      <td class="px-2 py-3 text-right tabular-nums ${o.delivered < o.total ? 'text-amber-700' : ''}" data-label="Delivered">${inr(o.delivered)}${o.delivery_recorded ? '' : '<div class="text-[11.5px] text-amber-700">not recorded</div>'}</td>
      <td class="px-2 py-3 text-right tabular-nums" data-label="Invoiced">${o.invoiced !== null ? inr(o.invoiced) : '—'}</td>
      <td class="pr-5 pl-2 py-3 text-right tabular-nums" data-label="Paid">${o.paid ? inr(o.paid) : '—'}</td></tr>`).join('');
    view.innerHTML = `<div class="space-y-6">
      <div class="flex flex-wrap items-end justify-between gap-4"><div><h1>Orders</h1>
        <p class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-slate-600">${dot('bg-rose-500', 'Mismatch')}${dot('bg-amber-400', 'In progress')}${dot('bg-emerald-400', 'Settled')}</p></div>
        <div class="flex gap-2 w-full sm:w-auto"><form id="po-search" class="flex-1"><input name="q" value="${esc(q)}" type="search" placeholder="PO number, vendor or cost centre" aria-label="Search purchase orders" class="w-full sm:w-64 rounded-lg border px-3 py-2 text-[13px]"></form>
          <a href="/purchase-orders/new" class="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold px-4 py-2 hover:bg-indigo-700">+ New PO</a></div></div>
      <section>${rows ? `<div class="overflow-x-auto"><table class="rtable tiles w-full text-sm"><thead class="text-left text-slate-500"><tr>
        <th class="pl-5 pr-2 py-2.5">PO</th><th class="px-2">Vendor</th><th class="px-2">Requested by</th><th class="px-2 text-center">Order value</th><th class="px-2 text-center">Delivered</th><th class="px-2 text-center">Invoiced</th><th class="pr-5 pl-2 text-center">Paid</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
        : `<div class="bg-white border rounded-xl">${emptyState(q ? 'No purchase order matches' : 'No purchase orders', q ? 'Try another search.' : 'Create one with "New PO". Invoices from active vendors are matched against them.')}</div>`}</section></div>`;
    qs('#po-search', view).addEventListener('submit', e => {
      e.preventDefault();
      const v = new FormData(e.target).get('q');
      navigate('/purchase-orders' + (v ? '?' + new URLSearchParams({ q: v }) : ''));
    });
  },
};
