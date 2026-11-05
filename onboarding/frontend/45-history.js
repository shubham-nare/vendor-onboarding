/* History (GET /api/v1/history): every decision and action, newest first, filtered by kind of record. */

const HISTORY_TABS = [['', 'Everything'], ['application', 'Vendor decisions'], ['invoice', 'Invoices and payments'], ['purchase_order', 'Purchase orders'], ['receipt', 'Deliveries'], ['change_request', 'Change requests']];

App.views['/audit'] = {
  title: 'History',
  async render(view) {
    const entity = new URLSearchParams(location.search).get('entity') || '';
    const d = await api('/history?' + new URLSearchParams({ entity }));
    const rows = d.events.map(r => `<tr class="${r.override ? 'bg-amber-50/50' : ''}">
      <td class="pl-5 pr-2 py-2.5 whitespace-nowrap text-slate-500">${esc(r.when.label)}</td>
      <td class="px-2 py-2.5" data-label="Who">${esc(r.who)}</td>
      <td class="px-2 py-2.5" data-label="What">${esc(r.action)}${r.override ? ' <span class="tag text-amber-700">override</span>' : ''}</td>
      <td class="px-2 py-2.5" data-label="Record">${r.href ? `<a class="text-indigo-700 hover:underline" href="${esc(r.href)}">${esc(r.record)}</a>` : esc(r.record)}${r.vendor ? ` · <a class="text-slate-500 hover:underline" href="/vendors/${esc(r.vendor.id)}">${esc(r.vendor.name)}</a>` : ''}</td>
      <td class="pr-5 pl-2 py-2.5 text-slate-600" data-label="Reason">${esc(r.reason || '—')}</td></tr>`).join('');
    view.innerHTML = `<div class="space-y-6"><h1>History</h1>
      <div class="flex flex-wrap gap-2 text-[12.5px]">${HISTORY_TABS.map(([k, l]) => `<a href="/audit${k ? '?entity=' + k : ''}" class="rounded-lg border px-3 py-1.5 ${entity === k ? 'border-indigo-500 bg-indigo-50 text-indigo-700 font-semibold' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}">${l}</a>`).join('')}</div>
      <section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]">
        <thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">When</th><th class="px-2">Who</th><th class="px-2">What</th><th class="px-2">Record</th><th class="pr-5 pl-2">Reason</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>` : emptyState('Nothing recorded yet', 'Decisions appear here as people take them.')}</section></div>`;
  },
};
