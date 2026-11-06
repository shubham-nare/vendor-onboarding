/* Vendor 360 (GET /api/v1/vendors/:id): who the vendor is, what proves it, who it's connected to, risk, invoices,
   documents, decisions and what to do next. Requesters get a reduced view (the server leaves the rest out). */

const VSTATE = { active: 'text-emerald-700', onboarding: 'text-indigo-600', rejected: 'text-rose-600', on_record: 'text-slate-600', inactive: 'text-slate-500' };
const EDGE_TONE = { verified: 'text-emerald-700', declared: 'text-slate-500', inferred: 'text-amber-700', unresolved: 'text-rose-700' };
const CARD_TONE = { green: 'text-emerald-700', red: 'text-rose-700', amber: 'text-amber-700', slate: 'text-slate-600' };
const PRIORITY = { urgent: ['bg-rose-600'], high: ['bg-amber-500'], normal: ['bg-indigo-500'], none: ['bg-emerald-500'] };
const LINE_COL = { verified: '#10B981', declared: '#94A3B8', unresolved: '#E11D48', inferred: '#D97706', context: '#CBD5E1' };

const basisTag = (b, label) => b === 'live' ? '<span class="tag dot text-emerald-700">Live source</span>'
  : b === 'simulated' ? '<span class="tag dot text-indigo-700">Registry</span>' : `<span class="tag text-slate-500">${esc(label)}</span>`;
const edgeTag = st => `<span class="tag dot ${EDGE_TONE[st] || 'text-slate-500'}">${esc(st)}</span>`;
const evLink = e => e ? `<a href="#ev-${e.id}" class="text-indigo-700 hover:underline" title="${esc(e.label)}">evidence #${e.id}</a>` : '';
const section = (id, title, body, right = '') => `<section class="bg-white border rounded-xl overflow-hidden min-w-0" id="${id}">
  <div class="px-4 sm:px-6 py-4 border-b border-slate-100 flex flex-wrap items-start justify-between gap-3"><h2 class="text-[16px]">${title}</h2>${right}</div>${body}</section>`;

function relationshipMap(m, v) {
  if (!m) return emptyState('No relationships recorded', 'Relationships appear once a check has run for this vendor.');
  const dash = st => st === 'context' ? ' stroke-dasharray="2 4"' : ['declared', 'inferred'].includes(st) ? ' stroke-dasharray="5 4"' : '';
  return `<svg viewBox="0 0 ${m.w} ${m.h}" class="w-full h-auto" role="img" aria-label="Relationship map of ${esc(v.name)}">
    ${m.lines.map(l => `<line x1="${l.x1}" y1="${l.y1}" x2="${l.x2}" y2="${l.y2}" stroke="${LINE_COL[l.status] || '#CBD5E1'}" stroke-width="${['unresolved', 'inferred'].includes(l.status) ? 2.2 : 1.5}"${dash(l.status)}/>`).join('')}
    ${m.ring.map(n => `<g><circle cx="${n.x}" cy="${n.y}" r="7" fill="#fff" stroke="${LINE_COL[n.status] || '#94A3B8'}" stroke-width="2"/>
      <text x="${n.x}" y="${(n.y - 12).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#475569" font-family="Verdana, sans-serif">${esc(n.kind)}</text>
      <text x="${n.x}" y="${(n.y + 20).toFixed(1)}" text-anchor="middle" font-size="9.5" fill="#64748B" font-family="Verdana, sans-serif">${esc(n.value)}</text></g>`).join('')}
    ${m.outer.map(o => `<g><a href="/vendors/${esc(o.vendor.id)}"><rect x="${(o.x - 78).toFixed(1)}" y="${(o.y - 15).toFixed(1)}" width="156" height="30" rx="8" fill="${o.actionable ? '#FFF1F2' : '#F8FAFC'}" stroke="${o.actionable ? '#FDA4AF' : '#CBD5E1'}"/>
      <text x="${o.x}" y="${(o.y + 4).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="${o.actionable ? '#9F1239' : '#475569'}" font-family="Verdana, sans-serif">${esc(o.vendor.name.slice(0, 24))}</text></a></g>`).join('')}
    <circle cx="${m.cx}" cy="${m.cy}" r="30" fill="#2950D3"/><text x="${m.cx}" y="${m.cy + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" font-family="Verdana, sans-serif">${esc(v.id)}</text></svg>`;
}

const edgeLine = (who, e) => `<span>${who}: ${esc(e.type)} · ${edgeTag(e.status)} · ${esc(e.basis_label)}${e.rule ? ` · rule ${esc(e.rule)}` : ''}${e.evidence ? ` · ${who === 'This vendor' ? evLink(e.evidence) : esc(e.evidence.label)}` : ''}${who === 'This vendor' ? '' : ` · since ${esc(e.since.label)}`}</span>`;

App.views['/vendors/:id'] = {
  title: p => p.id,
  async render(view, { id }) {
    const v = await api(`/vendors/${encodeURIComponent(id)}`);
    const parts = [];
    // header
    parts.push(`<div>${crumb('/vendors', 'Vendors', `<span class="mono">${esc(v.id)}</span>`)}
      <div class="mt-2 flex flex-wrap items-start gap-4">${monogram(v.name, 'h-14 w-14 text-[18px]')}<div class="min-w-0 flex-1"><h1 class="break-words">${esc(v.name)}</h1>
        <div class="mt-1.5 flex flex-wrap items-center gap-2 text-[12.5px] text-slate-500"><span class="tag dot ${VSTATE[v.status] || 'text-slate-500'}">${esc(v.status_label)}</span><span class="mono">${esc(v.id)}</span>
          ${v.erp_id ? `<span>· vendor master <span class="mono">${esc(v.erp_id)}</span></span>` : ''}${v.entity_type ? `<span>· ${esc(v.entity_type)}</span>` : ''}<span>· ${esc(v.country)}</span>
          ${v.open_flags ? `<span class="tag dot text-rose-600">${v.open_flags} open flag${v.open_flags === 1 ? '' : 's'}</span>` : ''}</div>
        <p class="mt-2 text-[12.5px] text-slate-500 max-w-3xl">The vendor ID is ours and never changes. Applications are matched to it by PAN; shared bank accounts, addresses or files never merge two vendors, they appear below as relationships to check.</p></div></div></div>`);
    if (v.cards) parts.push(`<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-[13px]">${v.cards.map(c => `<div class="bg-white border rounded-xl px-4 py-3 min-w-0"><div class="text-[12px] font-medium text-slate-500">${esc(c.label)}</div><div class="mt-0.5 font-semibold ${CARD_TONE[c.tone]}">${esc(c.value)}</div><div class="mt-0.5 text-[11.5px] text-slate-500 line-clamp-2">${esc(c.note)}</div></div>`).join('')}</div>`);
    // what to do next
    parts.push(section('next', 'What to do next', `<ol class="divide-y divide-slate-100">${v.next.map(a => `<li class="px-4 sm:px-6 py-3.5 flex gap-3"><span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${(PRIORITY[a.priority] || PRIORITY.normal)[0]}"></span>
      <div class="flex-1 min-w-0"><div class="flex flex-wrap items-baseline gap-x-2 gap-y-1"><span class="text-[14.5px] font-semibold text-slate-900">${esc(a.title)}</span>${a.needs_integration ? '<span class="tag text-amber-700">needs a real provider</span>' : ''}</div>
        ${a.detail ? `<p class="mt-0.5 text-[13px] text-slate-600">${esc(a.detail)}</p>` : ''}
        <p class="mt-1 text-[12px] text-slate-500"><b class="font-medium text-slate-600">Why:</b> ${esc(a.why)}${a.evidence.map(e => ' · ' + evLink(e)).join('')}${a.who.length ? ` · <b class="font-medium text-slate-600">Who:</b> ${a.who.map(esc).join(', ')}` : a.nobody ? ' · <b class="font-medium text-slate-600">Who:</b> nobody you can switch to right now' : ''}</p></div>
      ${a.href ? `<a href="${esc(a.href)}" class="self-center shrink-0 inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 hover:border-indigo-300 hover:text-indigo-700">Open ${icon('chev', 'h-3.5 w-3.5')}</a>` : ''}</li>`).join('')}</ol>`));
    // invoices and payments
    const inv = v.invoices;
    if (inv.show) {
      const money = inv.money ? `<dl class="grid grid-cols-3 gap-4 text-right text-[12px]"><div><dt class="text-slate-500">Approved, unpaid</dt><dd class="text-[15px] font-semibold tabular-nums">${inr(inv.money.approved_unpaid)}</dd></div>
        <div><dt class="text-slate-500">On hold</dt><dd class="text-[15px] font-semibold tabular-nums ${inv.money.on_hold ? 'text-amber-700' : ''}">${inr(inv.money.on_hold)}</dd></div><div><dt class="text-slate-500">Paid</dt><dd class="text-[15px] font-semibold tabular-nums text-emerald-700">${inr(inv.money.paid)}</dd></div></dl>` : '';
      const rb = inv.registration_bills;
      const body = inv.rows.length ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]"><thead class="text-left text-slate-500 bg-slate-50/70"><tr><th class="pl-4 sm:pl-6 pr-2 py-2">Invoice</th><th class="px-2">PO</th><th class="px-2 text-right">Amount</th><th class="px-2">Status</th><th class="pr-4 sm:pr-6 pl-2">Payment</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${inv.rows.map(b => `<tr class="hover:bg-slate-50/80 cursor-pointer" data-href="/bills/${b.id}"><td class="pl-4 sm:pl-6 pr-2 py-2.5"><a class="mono font-medium hover:text-indigo-700" href="/bills/${b.id}">${esc(b.number)}</a><div class="text-[11.5px] text-slate-500">${esc(b.date)} · ${esc(b.ref)}</div></td>
          <td class="px-2 py-2.5 mono text-[12px]" data-label="PO">${esc(b.po || '—')}</td><td class="px-2 py-2.5 text-right tabular-nums" data-label="Amount">${b.amount !== null ? inr(b.amount) : '—'}</td>
          <td class="px-2 py-2.5" data-label="Status"><span class="tag dot ${TONE_TEXT[b.tone] || 'text-slate-600'}">${esc(b.status)}</span></td>
          <td class="pr-4 sm:pr-6 pl-2 py-2.5 text-[12px] text-slate-600" data-label="Payment">${b.payment ? (b.payment.kind === 'hold' ? `<span class="text-amber-700">${esc(b.payment.text)}</span>` : esc(b.payment.text)) : '—'}</td></tr>`).join('')}</tbody></table></div>`
        : `<p class="px-4 sm:px-6 py-4 text-[13px] text-slate-500">No payable invoices yet. The vendor submits them from their portal against a purchase order.${rb ? ` The ${rb === 1 ? 'bill' : rb + ' bills'} sent with a registration ${rb === 1 ? 'is' : 'are'} kept under <a class="text-indigo-700 hover:underline" href="#documents">Documents</a> as registration evidence, not as payable invoices.` : ''}</p>`;
      parts.push(section('invoices', 'Invoices and payments', body + (inv.orders.length ? `<div class="border-t border-slate-100 px-4 sm:px-6 py-3 text-[12.5px]"><span class="font-semibold text-slate-700">Purchase orders:</span>${inv.orders.map(o => `<a class="ml-2 mono text-indigo-700 hover:underline" href="/purchase-orders/${o.id}">${esc(o.number)}</a>`).join('')}</div>` : ''), money));
    }
    if (v.full) {
      const idRows = v.identity.identifiers.map(i => `<tr class="${i.previous ? 'opacity-60' : ''}"><td class="pl-4 sm:pl-6 pr-2 py-2.5 w-28 text-slate-500 whitespace-nowrap">${esc(i.kind)}</td>
        <td class="px-2 py-2.5 mono text-[12.5px] break-words">${esc(i.value)}${i.full_bank ? ' <span class="tag text-emerald-700 ml-1 font-sans">full · Finance</span>' : ''}</td>
        <td class="pr-4 sm:pr-6 pl-2 py-2.5 text-right text-[11.5px] text-slate-500 whitespace-nowrap">${i.previous ? '<span class="tag text-slate-500">previous</span>' : 'since ' + esc(i.since.label)}</td></tr>`).join('')
        || '<tr><td class="px-6 py-6 text-[13px] text-slate-500">No identifiers recorded yet.</td></tr>';
      const contact = (label, val) => val ? `<tr><td class="pl-4 sm:pl-6 pr-2 py-2.5 w-28 text-slate-500 whitespace-nowrap">${label}</td><td class="px-2 py-2.5 text-[12.5px]" colspan="2">${esc(val)}</td></tr>` : '';
      const facts = v.facts.map(f => `<li class="px-4 sm:px-6 py-3 ${f.doubts.length ? 'bg-rose-50/50' : ''}">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5"><span class="w-28 text-[13px] font-medium text-slate-700">${esc(f.label)}</span><span class="mono text-[12.5px] break-words">${esc(f.value)}</span><span class="ml-auto">${proofChip({ level: f.level, name: f.level_name })}</span></div>
        <div class="mt-1.5 pl-0 sm:pl-[7.75rem] flex flex-wrap items-center gap-2 text-[12px] text-slate-500">${basisTag(f.basis, f.basis_label)} <span>${esc(f.source)}</span> · <span>${esc(f.where)}</span> · ${evLink(f.evidence)}
          ${f.note ? `<span class="w-full text-amber-700">${esc(f.note)}</span>` : ''}${f.recheck ? `<span class="w-full">Re-check due ${esc(f.recheck)}</span>` : ''}</div>
        ${f.doubts.map(d => `<div class="mt-1.5 sm:pl-[7.75rem] flex items-start gap-1.5 text-[12.5px] text-rose-700"><span><b class="font-semibold">In doubt despite its level:</b> ${esc(d)}</span></div>`).join('')}
        ${f.history.length ? `<details class="mt-1.5 sm:pl-[7.75rem] group"><summary class="text-[12px] text-indigo-700">${f.changed ? 'Changed value · ' : ''}${f.history.length} earlier observation${f.history.length === 1 ? '' : 's'}</summary>
          <ol class="mt-1.5 space-y-1 border-l-2 border-slate-200 pl-3">${f.history.map(o => `<li class="text-[12px] text-slate-600"><span class="mono">${esc(o.value)}</span> · ${esc(o.level)} · ${esc(o.basis)} · ${esc(o.where)} · ${esc(o.when)}</li>`).join('')}</ol></details>` : ''}</li>`).join('')
        || `<li class="px-6 py-6 text-[13px] text-slate-500">${v.origin === 'vendor_master' ? 'Known from the vendor master only: no checked evidence yet.' : 'No facts recorded yet.'}</li>`;
      parts.push(`<div class="grid xl:grid-cols-[1fr_1fr] gap-4 sm:gap-6">${section('identity', 'Identity', `<table class="w-full text-sm"><tbody class="divide-y divide-slate-100">${idRows}${contact('Contact', v.identity.contact)}${contact('Alternate contact', v.identity.alt_contact)}</tbody></table>`)}
        ${section('facts', 'Evidence and fact history', `<ul class="divide-y divide-slate-100">${facts}</ul>`)}</div>`);
      // relationships
      const act = v.connections.filter(c => c.actionable), ctx = v.connections.filter(c => !c.actionable);
      const actHtml = act.map(c => `<div class="mx-4 sm:mx-5 mb-3 rounded-lg border ${c.flagged ? 'border-rose-200 bg-rose-50/50' : 'border-amber-200 bg-amber-50/40'} p-3">
        <div class="flex flex-wrap items-center gap-2">${monogram(c.vendor.name, 'h-7 w-7 text-[10.5px]')}<a href="/vendors/${esc(c.vendor.id)}" class="font-semibold text-slate-900 hover:text-indigo-700">${esc(c.vendor.name)}</a>
          <span class="mono text-[11.5px] text-slate-500">${esc(c.vendor.id)}${c.vendor.erp_id ? ' · ' + esc(c.vendor.erp_id) : ''}</span>${c.flagged ? '<span class="tag dot text-rose-600">rule raised a flag</span>' : ''}</div>
        ${c.shared.filter(i => i.actionable).map(i => `<div class="mt-2 text-[12.5px] text-slate-700"><b class="font-semibold">${esc(i.what)}</b> <span class="mono text-slate-600">${esc(i.value)}</span>
          <div class="mt-1 grid gap-1 text-[12px] text-slate-500">${edgeLine('This vendor', i.mine)}${edgeLine(esc(c.vendor.name), i.theirs)}</div></div>`).join('')}</div>`).join('')
        || '<p class="px-4 sm:px-5 pb-4 text-[13px] text-slate-500">Nothing actionable: no other vendor shares this vendor\'s bank account or document files, and there is no identity conflict.</p>';
      const ctxHtml = ctx.map(c => `<div class="px-4 sm:px-5 pb-2.5 text-[12.5px] text-slate-600 flex flex-wrap items-center gap-x-2 gap-y-1"><a href="/vendors/${esc(c.vendor.id)}" class="font-medium text-slate-800 hover:text-indigo-700">${esc(c.vendor.name)}</a>
        ${c.shared.map(i => `<span class="tag text-slate-500" title="${esc(i.value)}">${esc(i.what)}</span>`).join('')}<span class="text-[11.5px] text-slate-400">ordinary overlap · not a risk by itself</span></div>`).join('')
        || '<p class="px-4 sm:px-5 pb-4 text-[13px] text-slate-500">No shared addresses, emails or phones.</p>';
      const edges = v.edges.map(e => `<tr class="${e.ended ? 'opacity-60' : ''}"><td class="pl-4 sm:pl-6 pr-2 py-2 whitespace-nowrap">${esc(e.type)}</td><td class="px-2 py-2"><span class="text-slate-500">${esc(e.kind)}</span> <span class="mono">${esc(e.value)}</span></td>
        <td class="px-2 py-2">${edgeTag(e.status)}</td><td class="px-2 py-2 whitespace-nowrap">${esc(e.basis_label)}</td><td class="px-2 py-2">${e.rule ? `rule ${esc(e.rule)} · ` : ''}${evLink(e.evidence)}${e.note ? `<div class="text-slate-500">${esc(e.note)}</div>` : ''}</td>
        <td class="pr-4 sm:pr-6 pl-2 py-2 whitespace-nowrap text-slate-500">from ${esc(e.since.label)}${e.until ? `<br>until ${esc(e.until.label)}` : ''}${e.checks ? `<br>checks ${esc(e.checks)}` : ''}</td></tr>`).join('');
      parts.push(section('relationships', 'Relationships', `<div class="grid lg:grid-cols-[1.1fr_1fr]"><div class="p-3 sm:p-4 border-b lg:border-b-0 lg:border-r border-slate-100 min-w-0">${relationshipMap(v.map, v)}</div>
        <div class="min-w-0"><div class="px-4 sm:px-5 pt-4 pb-2 text-[12px] font-semibold uppercase tracking-[.05em] text-slate-500">Needs a reviewer (${act.length})</div>${actHtml}
          <div class="px-4 sm:px-5 pt-2 pb-2 text-[12px] font-semibold uppercase tracking-[.05em] text-slate-500 border-t border-slate-100">For context (${ctx.length})</div>${ctxHtml}</div></div>
        <details class="border-t border-slate-100 group"><summary class="px-4 sm:px-6 py-3 text-[13px] font-medium text-indigo-700">All of this vendor's relationships, with provenance (${v.edges.length})</summary>
          <div class="overflow-x-auto"><table class="w-full text-[12.5px]"><thead class="text-left text-slate-500 bg-slate-50/70"><tr><th class="pl-4 sm:pl-6 pr-2 py-2">Relationship</th><th class="px-2">To</th><th class="px-2">Status</th><th class="px-2">Basis</th><th class="px-2">Provenance</th><th class="pr-4 sm:pr-6 pl-2">When</th></tr></thead>
          <tbody class="divide-y divide-slate-100">${edges}</tbody></table></div></details>`,
        `<div class="flex flex-wrap gap-1.5 text-[11.5px]">${['verified', 'declared', 'inferred', 'unresolved'].map(edgeTag).join('')}</div>`));
      // risk
      parts.push(section('risk', 'Risk flags', `<ul class="divide-y divide-slate-100">${v.risks.map(r => `<li class="px-4 sm:px-6 py-3.5 ${r.status === 'open' && r.fraud ? 'bg-rose-50/40' : ''}">
        <div class="flex flex-wrap items-center gap-2"><span class="tag dot ${r.status === 'open' ? 'text-rose-600' : 'text-emerald-700'}">${esc(r.status)}</span>${r.fraud ? '<span class="tag text-rose-600">fraud class</span>' : ''}<span class="text-[14px] font-semibold text-slate-900">${esc(r.title)}</span></div>
        <div class="mt-1 text-[12.5px] text-slate-500">${!r.mine && r.other ? `Raised on <a class="text-indigo-700 hover:underline" href="/vendors/${esc(r.other.id)}">${esc(r.other.name)}</a>, involving this vendor · ` : r.other ? `Involves <a class="text-indigo-700 hover:underline" href="/vendors/${esc(r.other.id)}">${esc(r.other.name)}</a> · ` : ''}rule ${esc(r.rule)} · check #${r.run_id} · opened ${esc(r.opened)}${r.evidence ? ' · ' + evLink(r.evidence) : ''}</div>
        ${r.action ? `<p class="mt-1.5 text-[13px] text-slate-700"><b class="font-semibold">Reviewer action:</b> ${esc(r.action)} <a class="ml-1 font-medium text-indigo-700 hover:underline" href="/runs/${r.run_id}#actions">Open the check</a></p>` : `<p class="mt-1.5 text-[13px] text-emerald-800">${icon('check', 'h-3.5 w-3.5 inline -mt-0.5')} ${esc(r.resolution || '')}</p>`}</li>`).join('') || '<li class="px-6 py-6 text-[13px] text-slate-500">No risk flags.</li>'}</ul>`));
      // documents
      const DSTATE = { current: 'text-emerald-700', superseded: 'text-slate-500', reused: 'text-rose-700', unreadable: 'text-amber-700' };
      parts.push(section('documents', 'Documents', v.documents.length ? `<div class="overflow-x-auto"><table class="rtable w-full text-[12.5px]"><thead class="text-left text-slate-500 bg-slate-50/70"><tr><th class="pl-4 sm:pl-6 pr-2 py-2">Document</th><th class="px-2">Status</th><th class="px-2">Read as</th><th class="px-2">Proof</th><th class="px-2">Supports</th><th class="pr-4 sm:pr-6 pl-2">File</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${v.documents.map(x => `<tr class="${x.status === 'superseded' ? 'opacity-60' : ''}">
          <td class="pl-4 sm:pl-6 pr-2 py-2.5"><div class="font-medium text-slate-800">${esc(x.title)}</div>${x.registration_bill ? '<div class="text-[11.5px] text-slate-500">registration evidence</div>' : ''}</td>
          <td class="px-2 py-2.5" data-label="Status"><span class="tag ${DSTATE[x.status] || ''}">${esc(x.status)}</span>${x.reused_by.length ? `<div class="text-rose-700 mt-0.5">also in ${x.reused_by.map(esc).join(', ')}</div>` : ''}</td>
          <td class="px-2 py-2.5" data-label="Read as">${esc(x.read_as)}<div class="text-slate-500">${esc(x.form)}${x.saved_reading ? ' · saved reading' : ''}</div></td>
          <td class="px-2 py-2.5" data-label="Proof">${x.proof ? proofChip(x.proof) : ''}${x.signed ? '<div class="text-emerald-700">signature valid</div>' : ''}${x.known_file ? '<div class="text-slate-500" title="This exact file is on record (matched by fingerprint), so visual checks are skipped. Its contents are not independently confirmed.">known file · not independently confirmed</div>' : ''}</td>
          <td class="px-2 py-2.5" data-label="Supports">${esc(x.supports.join(', ') || '—')}</td>
          <td class="pr-4 sm:pr-6 pl-2 py-2.5" data-label="File"><a class="text-indigo-700 hover:underline break-all" href="${esc(x.file.href)}" target="_blank" rel="noopener">${esc(x.file.name)}</a><div class="text-slate-500 mono">${x.file.size_kb ? x.file.size_kb + ' KB · ' : ''}${esc(x.file.fingerprint)}</div></td></tr>`).join('')}</tbody></table></div>`
        : `<p class="px-4 sm:px-6 py-4 text-[13px] text-slate-500">${v.origin === 'vendor_master' ? 'Known from the vendor master: no documents were uploaded through this system.' : 'No documents.'}</p>`));
    }
    // applications and decisions
    parts.push(section('applications', 'Applications and decisions', `<ul class="divide-y divide-slate-100">${v.applications.map(a => `<li class="px-4 sm:px-6 py-3.5">
      <div class="flex flex-wrap items-center gap-2"><span class="mono text-[12.5px] text-slate-700">${esc(a.ref)}</span>${statusBadge(a.status)}<span class="text-[12.5px] text-slate-500">${esc(a.came_in)} · ${esc(a.created)}</span></div>
      <div class="mt-2 flex flex-wrap gap-1.5">${a.checks.map(c => `<a href="/runs/${c.run_id}" class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/60 px-2.5 py-1 text-[12px] hover:border-indigo-300 hover:bg-white">Check #${c.run_id}${c.status ? ' · ' + esc(c.status) : ''}
        ${c.replay === null ? '' : `<span class="${c.replay ? 'text-emerald-600' : 'text-slate-400'}" title="${c.replay ? 'This decision replays exactly from its saved input' : 'Its saved input does not reproduce the decision exactly'}">${c.replay ? '↺' : '·'}</span>`}</a>`).join('')}</div></li>`).join('')
      || `<li class="px-6 py-6 text-[13px] text-slate-500">${v.origin === 'vendor_master' ? 'Known from the vendor master: no applications through this system.' : 'No applications.'}</li>`}</ul>
      ${v.decisions.length ? `<div class="border-t border-slate-100 px-4 sm:px-6 py-3.5"><div class="text-[12px] font-semibold uppercase tracking-[.05em] text-slate-500">Decisions by people</div>
        <ol class="mt-2 border-l-2 border-slate-200 ml-1 space-y-2">${v.decisions.map(a => `<li class="pl-4 text-[13px] relative"><span class="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-slate-500"></span><span class="text-[11.5px] text-slate-500">${esc(a.when)}</span><br>
          <b class="font-medium">${esc(a.who)}</b> <span class="text-slate-500">(${esc(a.role)})</span>: ${esc(a.action)}${a.comment ? ` · "${esc(a.comment)}"` : ''} <a class="text-indigo-700 hover:underline text-[12px]" href="/runs/${a.run_id}">check #${a.run_id}</a></li>`).join('')}</ol></div>` : ''}`));
    if (v.full) parts.push(`<details class="bg-white border rounded-xl group" id="evidence"><summary class="px-4 sm:px-6 py-4 flex items-center justify-between gap-2"><span><span class="text-[15px] font-semibold">Evidence register</span> <span class="text-[12.5px] text-slate-500">· ${v.evidence.length} items, never edited after they're recorded</span></span><span class="text-xs text-indigo-700 group-open:hidden">show</span><span class="text-xs text-indigo-700 hidden group-open:inline">hide</span></summary>
      <ul class="divide-y divide-slate-100 border-t border-slate-100">${v.evidence.map(e => `<li id="ev-${e.id}" class="px-4 sm:px-6 py-2.5 text-[12.5px] flex flex-wrap items-center gap-x-3 gap-y-1 target:bg-indigo-50"><span class="mono text-slate-400 w-10">#${e.id}</span>${basisTag(e.basis, e.basis_label)}<span class="text-slate-800">${esc(e.label)}</span>
        ${e.file ? `<a class="mono text-[11.5px] text-indigo-700 hover:underline" href="${esc(e.file.href)}" target="_blank" rel="noopener">sha256 ${esc(e.file.fingerprint)}</a>` : ''}<span class="ml-auto text-[11.5px] text-slate-400">${esc(e.captured)}</span></li>`).join('')}</ul></details>`);
    view.innerHTML = `<div class="space-y-6">${parts.join('')}</div>`;
    // evidence links open the register and jump to the item
    view.addEventListener('click', e => {
      const a = e.target.closest('a[href^="#ev-"]');
      if (!a) return;
      e.preventDefault();
      const target = qs(a.getAttribute('href'), view);
      if (target) { qs('#evidence', view).open = true; target.scrollIntoView({ block: 'center' }); target.classList.add('bg-indigo-50'); }
    });
  },
};
