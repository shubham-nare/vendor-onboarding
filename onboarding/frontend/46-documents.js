/* Documents (GET /api/v1/documents): every uploaded file, what it was read as and how well it is proven. */

const PROOF_TONE = { A0: 'text-slate-400', A1: 'text-sky-800', A2: 'text-blue-800', A3: 'text-indigo-600', A4: 'text-emerald-600' };
const proofChip = p => {
  const n = Number(p.level.slice(1)) || 0;
  return `<span class="ladder ${PROOF_TONE[p.level] || 'text-slate-400'}" title="${esc(p.level)}: ${esc(p.name)}"><span class="bars" aria-hidden="true">${[0, 1, 2, 3, 4].map(i => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</span><b>${esc(p.level)}</b><span>${esc(p.name)}</span></span>`;
};
const DOC_STATUS = {
  replaced: '<span class="tag text-slate-500">replaced</span>', wrong: '<span class="tag dot text-rose-700 bg-rose-50">wrong document</span>',
  verified: '<span class="tag dot text-emerald-700 bg-emerald-50">verified</span>', closer_look: '<span class="tag dot text-amber-700 bg-amber-50">needs a closer look</span>',
  not_usable: '<span class="tag dot text-rose-700 bg-rose-50">not usable</span>',
};

App.views['/documents'] = {
  title: 'Documents',
  async render(view) {
    const params = new URLSearchParams(location.search);
    const f = Object.fromEntries(['q', 'kind', 'show'].map(k => [k, params.get(k) || '']));
    const d = await api('/documents?' + new URLSearchParams(f));
    const filtered = f.q || f.kind || f.show;
    const rows = d.documents.map(x => `<tr class="hover:bg-slate-50/80 ${x.status === 'replaced' ? 'opacity-60' : ''}">
      <td class="pl-5 pr-2 py-3"><div class="font-medium text-slate-800">${esc(x.title)}</div><a class="text-[12px] text-indigo-700 hover:underline break-all" href="${esc(x.file.href)}" target="_blank" rel="noopener">${esc(x.file.name)}</a></td>
      <td class="px-2 py-3" data-label="Vendor">${x.vendor.id ? `<a class="hover:text-indigo-700" href="/vendors/${esc(x.vendor.id)}">${esc(x.vendor.name)}</a><div class="text-[11.5px] text-slate-500 mono">${esc(x.vendor.id)}</div>` : esc(x.vendor.name)}</td>
      <td class="px-2 py-3 mono text-[12px]" data-label="Application"><a class="hover:text-indigo-700" href="/runs/${x.application.run_id}">${esc(x.application.ref)}</a></td>
      <td class="px-2 py-3" data-label="Read as">${esc(x.read_as)}</td>
      <td class="px-2 py-3" data-label="Proof">${x.proof ? proofChip(x.proof) : '<span class="text-slate-400">—</span>'}</td>
      <td class="px-2 py-3" data-label="Status">${DOC_STATUS[x.status]}</td>
      <td class="pr-5 pl-2 py-3 text-right text-[12px] text-slate-500 whitespace-nowrap">${esc(x.uploaded.label)}</td></tr>`).join('');
    view.innerHTML = `<div class="space-y-6"><h1>Documents</h1>
      <form id="doc-filter" class="bg-white border rounded-xl p-3 sm:p-4 grid grid-cols-2 md:grid-cols-[minmax(14rem,2fr)_minmax(12rem,1fr)_minmax(10rem,1fr)_auto] gap-3 items-end text-[13px]">
        <label class="block col-span-2 md:col-span-1"><span class="text-[12px] font-medium text-slate-500">Search</span><input name="q" value="${esc(f.q)}" type="search" placeholder="Vendor, file name or VOB- reference" class="mt-1 w-full rounded-lg border px-3 py-2"></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">Type</span><select name="kind" class="mt-1 w-full rounded-lg border px-2 py-2 bg-white"><option value="">All types</option>${d.kinds.map(k => `<option value="${esc(k.key)}"${k.key === f.kind ? ' selected' : ''}>${esc(k.label)}</option>`).join('')}</select></label>
        <label class="block"><span class="text-[12px] font-medium text-slate-500">Show</span><select name="show" class="mt-1 w-full rounded-lg border px-2 py-2 bg-white"><option value=""${f.show ? '' : ' selected'}>Current only</option><option value="all"${f.show === 'all' ? ' selected' : ''}>Including replaced</option></select></label>
        <div class="flex gap-2 col-span-2 md:col-span-1"><button class="rounded-lg bg-indigo-600 text-white font-semibold px-4 py-2 hover:bg-indigo-700">Apply</button>${filtered ? '<a href="/documents" class="rounded-lg border px-3 py-2 text-slate-600 hover:border-slate-400">Clear</a>' : ''}</div></form>
      <section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="px-5 py-2.5 border-b border-slate-100 text-[12.5px] text-slate-500">${d.documents.length} document${d.documents.length === 1 ? '' : 's'}</div>
        <div class="overflow-x-auto"><table class="rtable w-full text-[13px]"><thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">Document</th><th class="px-2">Vendor</th><th class="px-2">Application</th><th class="px-2">Read as</th><th class="px-2">Proof</th><th class="px-2">Status</th><th class="pr-5 pl-2 text-right">Uploaded</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>` : emptyState(f.q || f.kind ? 'No documents match' : 'No documents yet', f.q || f.kind ? 'Try another filter.' : 'Files appear here as vendors register.')}</section></div>`;
    qs('#doc-filter', view).addEventListener('submit', e => {
      e.preventDefault();
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
      navigate('/documents' + (p.toString() ? '?' + p : ''));
    });
  },
};
