/* Relationships (GET /api/v1/relationships): flags raised by the rules, and details shared between vendors. */

const vendorLink = (v, hash = '') => v ? `<a class="text-indigo-700 hover:underline" href="/vendors/${esc(v.id)}${hash}">${esc(v.name)}</a>` : '';

App.views['/relationships'] = {
  title: 'Relationships',
  async render(view) {
    const d = await api('/relationships');
    const flags = d.flags.map(r => `<li class="px-4 sm:px-5 py-3.5 ${r.status === 'open' && r.severity === 'fraud' ? 'bg-rose-50/40' : ''}">
      <div class="flex flex-wrap items-center gap-2"><span class="tag dot ${r.status === 'open' ? 'text-rose-700' : 'text-emerald-700'}">${esc(r.status)}</span><span class="text-[14px] font-medium">${esc(r.title)}</span></div>
      <div class="mt-1 text-[12.5px] text-slate-500">${vendorLink(r.vendor, '#risk')}${r.related ? ' ↔ ' + vendorLink(r.related) : ''} · rule ${esc(r.rule)} · ${esc(r.opened.label)}</div>
      <p class="mt-1 text-[13px] text-slate-700">${r.action ? `<b class="font-semibold">Reviewer action:</b> ${esc(r.action)}` : esc(r.resolution || '')}</p></li>`).join('');
    const shared = d.shared.map(x => `<li class="px-4 sm:px-5 py-3.5">
      <div class="flex flex-wrap items-center gap-2"><span class="tag ${x.needs_reviewer ? 'text-amber-700' : 'text-slate-500'}">${x.needs_reviewer ? 'needs a reviewer' : 'context'}</span><span class="text-[14px] font-medium">${esc(x.label)}</span><span class="mono text-[12.5px] text-slate-600">${esc(x.value)}</span></div>
      <ul class="mt-1.5 space-y-1 text-[12.5px]">${x.vendors.map(m => `<li>${vendorLink(m.vendor, '#relationships')} · <span class="text-slate-500">${esc(m.status)} · ${esc(m.basis)} · since ${esc(m.since.label)}</span></li>`).join('')}</ul>
      <p class="mt-1.5 text-[12.5px] text-slate-600">${esc(x.why)}</p></li>`).join('');
    view.innerHTML = `<div class="space-y-6"><h1>Relationships</h1>
      <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Flags raised by the rules</h2></div>
        ${flags ? `<ul class="divide-y divide-slate-100">${flags}</ul>` : '<p class="px-5 py-4 text-[13px] text-slate-500">No flags.</p>'}</section>
      <section class="bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Shared details between vendors</h2></div>
        ${shared ? `<ul class="divide-y divide-slate-100">${shared}</ul>` : emptyState('No shared details', 'No two vendors share a bank account, document, address, email or phone.')}</section></div>`;
  },
};
