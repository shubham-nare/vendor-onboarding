/* Invoices (GET /api/v1/invoices): search, vendor, amount range, sort and status chips, all kept in the address bar. */

const TONE_TEXT = { slate: 'text-slate-600', green: 'text-emerald-700', red: 'text-rose-700', amber: 'text-amber-700' };
const INVOICE_SORTS = [['', 'Most urgent first'], ['new', 'Newest first'], ['old', 'Oldest first'], ['amount_desc', 'Amount: high to low'], ['amount_asc', 'Amount: low to high'], ['vendor', 'Vendor A–Z']];

App.views['/invoices'] = {
  title: 'Invoices',
  async render(view) {
    const params = new URLSearchParams(location.search);
    const f = Object.fromEntries(['status', 'q', 'vendor', 'amin', 'amax', 'sort'].map(k => [k, params.get(k) || '']));
    const d = await api('/invoices?' + new URLSearchParams(f));
    const others = Object.fromEntries(Object.entries(f).filter(([k, v]) => v && k !== 'status'));
    const link = st => '/invoices' + ((st || Object.keys(others).length) ? '?' + new URLSearchParams({ ...others, ...(st ? { status: st } : {}) }) : '');
    const chip = (on, href, inner) => `<a href="${href}" class="rounded-lg border px-3 py-1.5 ${on ? 'border-indigo-500 bg-indigo-50 text-indigo-700 font-semibold' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}">${inner}</a>`;
    const rows = d.invoices.map(x => `<tr class="group cursor-pointer row-${x.tone}" data-href="/bills/${x.id}">
      <td class="pl-5 pr-2 py-3 whitespace-nowrap"><a href="/bills/${x.id}" class="font-medium text-slate-900 group-hover:text-indigo-700 mono text-[12.5px]">${esc(x.invoice_number || 'being read…')}</a>
        <div class="text-[11.5px] text-slate-500"><span class="mono">${esc(x.ref)}</span> · ${esc(x.created.label)}</div></td>
      <td class="px-2 py-3" data-label="Vendor">${x.vendor.profile ? `<a href="/vendors/${esc(x.vendor.profile)}" class="hover:text-indigo-700">${esc(x.vendor.name)}</a>` : esc(x.vendor.name)}<div class="text-[11.5px] text-slate-500 mono">${esc(x.vendor.id)}</div></td>
      <td class="px-2 py-3 mono text-[12px]" data-label="PO">${esc(x.po_number || '—')}</td>
      <td class="px-2 py-3 text-right tabular-nums whitespace-nowrap" data-label="Amount">${x.amount !== null ? inr(x.amount) : '—'}</td>
      <td class="px-2 py-3" data-label="Status"><span class="tag dot ${TONE_TEXT[x.tone] || 'text-slate-600'}">${esc(x.status)}</span></td>
      <td class="pr-5 pl-2 py-3 text-[12.5px] max-w-[22rem]" data-label="Next action">${x.next ? `<div class="font-medium text-slate-800">${esc(x.next.title)}</div><div class="text-slate-500 line-clamp-2">${esc(x.next.detail)}</div>` : '<span class="text-slate-400">—</span>'}</td></tr>`).join('');
    const filtered = Object.values(f).some(Boolean);
    view.innerHTML = `<div class="space-y-6"><h1>Invoices</h1>
      <form id="inv-filter" class="bg-white border rounded-xl p-3 sm:p-4 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-[minmax(14rem,1.4fr)_minmax(12rem,1fr)_8rem_8rem_minmax(11rem,.9fr)_auto] gap-3 items-end text-[13px]">
        <label class="block col-span-2 md:col-span-1"><span class="text-[12px] font-medium text-slate-500">Search</span>
          <input name="q" value="${esc(f.q)}" type="search" placeholder="Invoice, PO, BILL- or vendor" class="mt-1 w-full rounded-lg border px-3 py-2"></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">Vendor</span>
          <select name="vendor" class="mt-1 w-full rounded-lg border px-2 py-2 bg-white"><option value="">All vendors</option>
          ${d.vendors.map(v => `<option value="${esc(v.id)}"${v.id === f.vendor ? ' selected' : ''}>${esc(v.name)}</option>`).join('')}</select></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">Amount from ₹</span>
          <input name="amin" value="${esc(f.amin)}" inputmode="decimal" placeholder="0" class="mt-1 w-full rounded-lg border px-3 py-2 text-right tabular-nums"></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">to ₹</span>
          <input name="amax" value="${esc(f.amax)}" inputmode="decimal" placeholder="any" class="mt-1 w-full rounded-lg border px-3 py-2 text-right tabular-nums"></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">Sort</span>
          <select name="sort" class="mt-1 w-full rounded-lg border px-2 py-2 bg-white">${INVOICE_SORTS.map(([k, l]) => `<option value="${k}"${k === f.sort ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
        <div class="flex gap-2 col-span-2 md:col-span-1"><button class="rounded-lg bg-indigo-600 text-white font-semibold px-4 py-2 hover:bg-indigo-700">Apply</button>
          ${filtered ? '<a href="/invoices" class="rounded-lg border px-3 py-2 text-slate-600 hover:border-slate-400">Clear</a>' : ''}</div>
      </form>
      <div class="flex flex-wrap gap-2 text-[12.5px]" aria-label="Filter by status">${chip(!f.status, link(''), 'All')}
        ${d.chips.map(c => chip(f.status === c.status, link(c.status), `<span class="inline-block h-2 w-2 rounded-full bg-current mr-1 ${TONE_TEXT[c.tone] || ''}"></span>${esc(c.status)} <span class="tabular-nums text-slate-400">${c.count}</span>${c.sum !== null ? ` · <span class="tabular-nums">${inr(c.sum)}</span>` : ''}`)).join('')}</div>
      <section>${rows ? `<div class="px-1 py-1 flex flex-wrap justify-between gap-2 text-[13px] text-slate-500"><span>${d.invoices.length} invoice${d.invoices.length === 1 ? '' : 's'}</span>${d.total !== null ? `<span>Total <b class="text-slate-800 tabular-nums">${inr(d.total)}</b></span>` : ''}</div>
        <div class="overflow-x-auto"><table class="rtable tiles w-full text-sm"><thead class="text-left text-slate-500"><tr><th class="pl-5 pr-2 py-2.5">Invoice</th><th class="px-2">Vendor</th><th class="px-2">PO</th><th class="px-2 text-right">Amount</th><th class="px-2">Status</th><th class="pr-5 pl-2">Next action</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
        : `<div class="bg-white border rounded-xl">${emptyState(filtered ? 'No invoices match' : 'No invoices yet', filtered ? 'Try another filter.' : 'Active vendors submit invoices from their portal; each is checked against its purchase order here.')}</div>`}</section></div>`;
    qs('#inv-filter', view).addEventListener('submit', e => {
      e.preventDefault();
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
      if (f.status) p.set('status', f.status);
      navigate('/invoices' + (p.toString() ? '?' + p : ''));
    });
  },
};
