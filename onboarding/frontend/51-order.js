/* One purchase order (GET /api/v1/purchase-orders/:id, POST .../deliveries) and a new order (GET .../options, POST /purchase-orders). */

const crumb = (href, label, here) => `<div class="text-[13px] font-medium text-slate-500 flex items-center gap-1.5"><a href="${href}" class="hover:text-slate-900">${label}</a> ${icon('chev', 'h-3.5 w-3.5 text-slate-400')} <span class="text-slate-800">${here}</span></div>`;
const PO_STATE = { open: ['Open', 'text-amber-700 bg-amber-50'], closed: ['Closed', 'text-emerald-700 bg-emerald-50'], cancelled: ['Cancelled', 'text-rose-700 bg-rose-50'] };
const num = n => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });

// a form whose errors show inside it; `send` gets the form and returns a promise
function wireForm(form, send) {
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const err = qs('[data-error]', form), btns = qsa('button:not([type=button])', form);
    btns.forEach(b => { b.disabled = true; });
    if (err) err.hidden = true;
    try { await send(form, e.submitter); }
    catch (x) { if (err) { err.textContent = x.message; err.hidden = false; } }
    finally { btns.forEach(b => { b.disabled = false; }); }
  });
}

App.views['/purchase-orders/:id'] = {
  title: p => `Order ${p.id}`,
  async render(view, { id }) {
    const d = await api(`/purchase-orders/${encodeURIComponent(id)}`), t = d.totals;
    const st = PO_STATE[d.status] || [d.status, 'text-slate-600 bg-slate-50'];
    const facts = [['Cost centre', d.cost_centre || '—'], ['Requested by', d.requested_by || '—'], ['Approved by', d.approved_by || '—'],
                   ['Service period', d.service_period || '—'], ['Pays into', d.pays_into], ['Deliveries', `${d.deliveries.length} recorded`]];
    const lineState = l => l.delivered >= l.quantity ? '<span class="tag dot text-emerald-700 bg-emerald-50">Delivered</span>'
      : l.delivered > 0 ? '<span class="tag dot text-amber-700 bg-amber-50">Partly delivered</span>' : '<span class="tag dot text-rose-700 bg-rose-50">Not delivered</span>';
    view.innerHTML = `<div class="space-y-6"><div>${crumb('/purchase-orders', 'Orders', `<span class="mono">${esc(d.number)}</span>`)}
      <div class="mt-1.5 flex flex-wrap items-start justify-between gap-4"><div>
        <h1 class="flex flex-wrap items-center gap-3">${esc(d.number)} <span class="tag dot ${st[1]} !text-[12px]">${esc(st[0])}</span></h1>
        <p class="mt-1 text-[13.5px] text-slate-600">${d.vendor.id ? `<a class="font-medium text-indigo-700 hover:underline" href="/vendors/${esc(d.vendor.id)}">${esc(d.vendor.name)}</a>` : esc(d.vendor.name)} · <span class="mono">${esc(d.vendor.gstin)}</span></p></div>
        <dl class="grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-2 text-right">
          <div><dt class="text-[12px] font-medium text-slate-500">Order value</dt><dd class="text-[22px] font-semibold tabular-nums">${inr(t.order)}</dd></div>
          <div><dt class="text-[12px] font-medium text-slate-500">Delivered</dt><dd class="text-[22px] font-semibold tabular-nums ${t.delivered >= t.order - 0.5 ? 'text-emerald-700' : 'text-amber-700'}">${inr(t.delivered)}</dd></div>
          <div><dt class="text-[12px] font-medium text-slate-500">Invoiced</dt><dd class="text-[22px] font-semibold tabular-nums ${t.invoiced > t.delivered + 0.5 ? 'text-rose-700' : ''}">${inr(t.invoiced)}</dd></div>
          <div><dt class="text-[12px] font-medium text-slate-500">Paid</dt><dd class="text-[22px] font-semibold tabular-nums ${t.paid ? 'text-emerald-700' : ''}">${inr(t.paid)}</dd></div></dl></div></div>
      <dl class="bg-white border rounded-xl px-4 sm:px-6 py-3 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-x-6 gap-y-3 text-[13px]">${facts.map(([k, v]) => `<div class="min-w-0"><dt class="text-slate-500 text-[12px]">${k}</dt><dd class="mt-0.5 font-medium truncate">${esc(v)}</dd></div>`).join('')}</dl>
      <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-6 py-4 border-b border-slate-100"><h2 class="text-[16px]">Lines and delivery</h2></div>
        <div class="overflow-x-auto"><table class="w-full text-[13px]"><thead class="text-left text-slate-500 bg-slate-50/70"><tr><th class="pl-4 sm:pl-6 pr-2 py-2">Line</th><th class="px-2">Delivery</th><th class="px-2 text-right">Ordered</th><th class="px-2 text-right">Delivered</th><th class="px-2 text-right">Unit price</th><th class="px-2 text-right">GST</th><th class="pr-4 sm:pr-6 pl-2 text-right">Value incl. GST</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${d.lines.map(l => `<tr><td class="pl-4 sm:pl-6 pr-2 py-2.5">${esc(l.description)}</td><td class="px-2 py-2.5 whitespace-nowrap">${lineState(l)}</td>
          <td class="px-2 text-right tabular-nums">${num(l.quantity)} ${esc(l.unit)}</td>
          <td class="px-2 text-right tabular-nums font-semibold ${l.delivered >= l.quantity ? 'text-emerald-700' : l.delivered > 0 ? 'text-amber-700' : 'text-rose-700'}">${num(l.delivered)}</td>
          <td class="px-2 text-right tabular-nums">${inr(l.unit_price)}</td><td class="px-2 text-right">${num(l.tax_rate)}%</td><td class="pr-4 sm:pr-6 pl-2 text-right tabular-nums">${inr(l.value)}</td></tr>`).join('')}</tbody></table></div></section>
      <div class="grid lg:grid-cols-2 xl:grid-cols-3 gap-6 items-start">
        <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-6 py-4 border-b border-slate-100"><h2 class="text-[16px]">Deliveries</h2></div>
          <ul class="divide-y divide-slate-100">${d.deliveries.length ? d.deliveries.map(g => `<li class="px-4 sm:px-6 py-2.5 text-[13px]"><span class="mono font-medium">${esc(g.number)}</span> · ${g.kind === 'goods' ? 'goods received' : 'service confirmed'} on ${esc(g.on)} by ${esc(g.by || '—')}${g.note ? `<div class="text-slate-500">${esc(g.note)}</div>` : ''}</li>`).join('')
            : '<li class="px-6 py-4 text-[13px] text-amber-700">Nothing recorded yet: invoices against this order will wait for review.</li>'}</ul></section>
        <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-6 py-4 border-b border-slate-100"><h2 class="text-[16px]">Record a delivery</h2><p class="text-[12.5px] text-slate-500 mt-0.5">By the person who requested the order, or a reviewer.</p></div>
          <form id="delivery" class="p-4 sm:p-6 space-y-3 text-[13px]">
            <div class="grid sm:grid-cols-2 gap-3"><label class="block">Type<select name="kind" class="mt-1 w-full rounded-md border px-2 py-1.5"><option value="service">Service confirmation</option><option value="goods">Goods receipt</option></select></label>
              <label class="block">Date<input type="date" name="received_on" class="mt-1 w-full rounded-md border px-2 py-1.5"></label></div>
            ${d.lines.map(l => `<label class="flex items-center justify-between gap-3"><span class="text-slate-600">${esc(l.description.slice(0, 70))}</span><input name="qty_${l.id}" data-line="${l.id}" inputmode="decimal" placeholder="qty" class="w-24 rounded-md border px-2 py-1.5 text-right"></label>`).join('')}
            <input name="note" placeholder="Note (optional)" class="w-full rounded-md border px-2 py-1.5">
            <p class="text-[13px] text-rose-700" data-error hidden></p>
            <div class="flex justify-end"><button class="rounded-lg border border-indigo-300 bg-white px-4 py-2 font-semibold text-indigo-700 hover:bg-indigo-50">Record delivery</button></div></form></section>
        <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-6 py-4 border-b border-slate-100"><h2 class="text-[16px]">Invoices</h2></div>
          <ul class="divide-y divide-slate-100">${d.invoices.length ? d.invoices.map(b => `<li><a href="/bills/${b.id}" class="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-6 py-2.5 text-[13px] hover:bg-slate-50"><span class="mono font-medium">${esc(b.number)}</span><span class="ml-auto tabular-nums">${b.amount !== null ? inr(b.amount) : '—'}</span><span class="tag dot ${TONE_TEXT[b.tone] || ''}">${esc(b.status)}</span></a></li>`).join('')
            : '<li class="px-6 py-4 text-[13px] text-slate-500">No invoices yet.</li>'}</ul>
          ${d.history.length ? `<div class="border-t border-slate-100 px-4 sm:px-6 py-3"><div class="text-[12px] font-semibold text-slate-600">History</div><ol class="mt-1.5 space-y-1 text-[12.5px] text-slate-600">${d.history.map(e => `<li>${esc(e.when.label)} · ${esc(e.who)} · ${esc(e.what)} ${esc(e.record)}</li>`).join('')}</ol></div>` : ''}</section>
      </div></div>`;
    wireForm(qs('#delivery', view), async f => {
      const quantities = {};
      qsa('[data-line]', f).forEach(i => { if (i.value.trim()) quantities[i.dataset.line] = Number(i.value.replace(/,/g, '')); });
      await api(`/purchase-orders/${d.id}/deliveries`, { method: 'POST', body: { kind: f.kind.value, received_on: f.received_on.value, note: f.note.value, quantities } });
      await reload();
    });
  },
};

App.views['/purchase-orders/new'] = {
  title: 'New purchase order',
  async render(view) {
    const d = await api('/purchase-orders/options'), me = App.session.actor.id;
    const people = sel => d.employees.map(e => `<option value="${e.id}"${sel === e.id ? ' selected' : ''}>${esc(e.name)} · ${esc(e.department)}</option>`).join('');
    const row = i => `<tr class="${i > 2 ? 'hidden' : ''}" data-row="${i}">
      <td class="py-1 pr-2"><input name="desc" class="w-full rounded-md border px-2 py-1.5"${i === 1 ? ' required' : ''}></td>
      <td class="py-1 px-1"><input name="qty" inputmode="decimal" class="w-full rounded-md border px-2 py-1.5"></td>
      <td class="py-1 px-1"><input name="unit" class="w-full rounded-md border px-2 py-1.5" placeholder="job"></td>
      <td class="py-1 px-1"><input name="price" inputmode="decimal" class="w-full rounded-md border px-2 py-1.5"></td>
      <td class="py-1 pl-1"><input name="tax" value="18" inputmode="decimal" class="w-full rounded-md border px-2 py-1.5"></td></tr>`;
    view.innerHTML = `<div class="space-y-6 max-w-4xl"><div>${crumb('/purchase-orders', 'Orders', 'New')}<h1 class="mt-1">New purchase order</h1>
        <p class="text-slate-500 text-[14px] mt-1.5">Only active vendors can receive orders. The payee account is the one verified at onboarding; it can't be changed here.</p></div>
      <form id="new-po" class="bg-white border rounded-xl p-4 sm:p-6 space-y-5 text-sm">
        <div class="grid sm:grid-cols-2 gap-4">
          <label class="block">PO number<input name="po_number" required class="mt-1 w-full rounded-md border px-3 py-2 mono uppercase" placeholder="PO-2026-0170"></label>
          <label class="block">Vendor<select name="vendor_id" required class="mt-1 w-full rounded-md border px-3 py-2">${d.vendors.length ? d.vendors.map(v => `<option value="${esc(v.id)}">${esc(v.name)} · ${esc(v.id)}</option>`).join('') : '<option value="">No active vendors</option>'}</select></label>
          <label class="block">Cost centre<input name="cost_centre" class="mt-1 w-full rounded-md border px-3 py-2 mono uppercase" placeholder="PL2-FACILITIES"></label>
          <div class="grid grid-cols-2 gap-3"><label class="block">Service from<input type="date" name="service_from" class="mt-1 w-full rounded-md border px-3 py-2"></label>
            <label class="block">Service to<input type="date" name="service_to" class="mt-1 w-full rounded-md border px-3 py-2"></label></div>
          <label class="block">Requested by<select name="requester_id" class="mt-1 w-full rounded-md border px-3 py-2">${people(null)}</select></label>
          <label class="block">Approved by<select name="approver_id" class="mt-1 w-full rounded-md border px-3 py-2">${people(me)}</select></label></div>
        <div><div class="font-semibold">Lines</div><div class="mt-2 overflow-x-auto"><table class="w-full text-[13px]" id="polines">
          <thead class="text-left text-slate-500"><tr><th class="py-1 pr-2 font-medium">Description</th><th class="py-1 px-1 font-medium w-20">Qty</th><th class="py-1 px-1 font-medium w-24">Unit</th><th class="py-1 px-1 font-medium w-32">Unit price (₹)</th><th class="py-1 pl-1 font-medium w-20">GST %</th></tr></thead>
          <tbody>${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(row).join('')}</tbody></table></div>
          <button type="button" id="addline" class="mt-2 text-[12.5px] font-medium text-indigo-700 hover:underline">+ Add a line</button></div>
        <p class="text-[13px] text-rose-700" data-error hidden></p>
        <div class="flex justify-end"><button class="rounded-lg bg-indigo-600 text-white font-semibold px-5 py-2.5 hover:bg-indigo-700">Create purchase order</button></div></form></div>`;
    qs('#addline', view).onclick = () => { const next = qs('#polines tr.hidden', view); if (next) { next.classList.remove('hidden'); qs('input', next).focus(); } };
    wireForm(qs('#new-po', view), async f => {
      const n = v => Number(String(v).replace(/,/g, ''));
      const lines = qsa('tr[data-row]', f).map(r => Object.fromEntries(qsa('input', r).map(i => [i.name, i.value.trim()])))
        .filter(l => l.desc).map(l => ({ description: l.desc, quantity: n(l.qty), unit: l.unit, unit_price: n(l.price), tax_rate: n(l.tax || 18) }));
      const r = await api('/purchase-orders', { method: 'POST', body: {
        po_number: f.po_number.value.trim().toUpperCase(), vendor_id: f.vendor_id.value, cost_centre: f.cost_centre.value.trim().toUpperCase(),
        requester_id: Number(f.requester_id.value) || null, approver_id: Number(f.approver_id.value) || null,
        service_from: f.service_from.value, service_to: f.service_to.value, lines } });
      navigate(r.next);
    });
  },
};
