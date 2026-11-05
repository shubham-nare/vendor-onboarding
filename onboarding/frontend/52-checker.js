/* Checker (POST /api/v1/check, GET /api/v1/check/sample): digital signature, file facts and signals, no AI. */

const STAMP = {
  verified: ['text-emerald-600', 'Signature verified'], broken: ['text-rose-600', 'Signature broken'], edited: ['text-rose-600', 'Likely edited'],
  unsigned_pdf: ['text-amber-600', 'No signature'], image: ['text-slate-500', 'Image · unsigned'],
};
const SEVERITY = { info: 'text-slate-500', warn: 'text-amber-700', vendor: 'text-amber-800', review: 'text-amber-700', fraud: 'text-white bg-rose-600 !border-rose-600' };

function checkCard(r) {
  const s = r.signature, [tone, label] = STAMP[r.stamp];
  const extra = r.stamp === 'verified' ? `<span class="text-[9px] tracking-[.12em] border-l-2 border-current pl-2 leading-tight">GSTN<br>${esc(s.signed_at || '')}</span>`
    : r.stamp === 'edited' ? '<span class="text-[9px] tracking-[.12em] border-l-2 border-current pl-2 leading-tight">no<br>signature</span>' : '';
  const sigRows = [['Signer', s.signer ? s.signer + (s.signer_org ? ` (${s.signer_org})` : '') : ''], ['Signed', s.signed_at], ['Format', s.format],
                   ['Covers file', s.covers_whole_file === null || s.covers_whole_file === undefined ? '' : s.covers_whole_file ? 'whole file' : 'NO: content was added after signing'],
                   ['Chain', s.chain.join(' → ')], ['Error', s.error]].filter(([, v]) => v);
  return `<div class="bg-white rounded-xl border p-4 sm:p-5 min-w-0">
    <div class="flex flex-wrap items-start justify-between gap-2"><div class="font-medium text-sm break-all">${esc(r.file)}</div>${proofChip(r.proof)}</div>
    <div class="mono text-[11px] text-slate-500 mt-0.5">${esc(r.mime)} · ${r.size_kb} KB</div>
    <div class="mt-5 mb-1"><span class="stamp stamp-land ${tone} text-[15px] sm:text-[17px] max-w-full">${label}${extra}</span></div>
    <div class="mt-4 rounded-lg p-3 text-sm ${s.verified ? 'bg-emerald-50 border border-emerald-200' : s.present ? 'bg-rose-50 border border-rose-200' : 'bg-slate-50 border'}">
      <div class="font-medium">Digital signature</div>
      ${!s.present ? `<div class="text-xs text-slate-600 mt-1">None. ${r.kind === 'pdf' ? 'A certificate downloaded from the GST portal is normally signed; editors like Canva remove the signature.' : 'Images cannot carry one.'}</div>`
        : `<div class="text-xs mt-1">${s.verified ? 'Intact and cryptographically valid: not a byte has changed since it was signed.' : s.intact === false ? 'BROKEN: the file was changed after it was signed.' : 'Present but could not be verified.'}</div>
          <dl class="text-xs mt-2 grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-0.5">${sigRows.map(([k, v]) => `<dt class="text-slate-500">${k}</dt><dd class="break-words ${k === 'Error' ? 'text-rose-700' : ''}">${esc(v)}</dd>`).join('')}</dl>`}</div>
    <div class="mt-4"><div class="text-sm font-medium">File facts</div><dl class="text-xs mt-1 grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-0.5">${r.facts.map(f => `<dt class="text-slate-500">${esc(f.label)}</dt><dd class="break-all">${esc(f.value)}</dd>`).join('')}</dl></div>
    <div class="mt-4"><div class="text-sm font-medium">Signals</div><ul class="mt-1 space-y-1.5">${r.signals.length ? r.signals.map(x => `<li class="text-xs flex gap-2"><span class="tag ${SEVERITY[x.severity] || 'text-slate-500'} !text-[9.5px] shrink-0 self-start mt-px">${esc(x.severity)}</span><span>${esc(x.title)}${x.detail ? `<span class="block text-slate-500">${esc(x.detail)}</span>` : ''}</span></li>`).join('') : '<li class="text-xs text-emerald-700">None.</li>'}</ul></div></div>`;
}

App.views['/check'] = {
  title: 'Checker',
  async render(view) {
    view.innerHTML = `<div><div class="kicker">Forensics, no AI</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Checker</h1>
      <form id="check-form" class="mt-5 bg-white rounded-xl border p-4 grid gap-3 sm:flex sm:flex-wrap sm:items-center sm:gap-4 text-sm">
        <label class="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 min-w-0">File 1 <input type="file" name="file_a" accept=".pdf,.jpg,.jpeg,.png" class="text-xs max-w-full"></label>
        <label class="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2 min-w-0">File 2 <input type="file" name="file_b" accept=".pdf,.jpg,.jpeg,.png" class="text-xs max-w-full"></label>
        <label class="flex items-center gap-2 py-1"><input type="checkbox" name="with_sample" value="1"> include the genuine public sample</label>
        <button class="sm:ml-auto w-full sm:w-auto rounded-md bg-indigo-600 text-white px-4 py-2.5 sm:py-2">Check</button>
        <button type="button" id="just-sample" class="text-xs text-indigo-700 underline py-1 text-center sm:text-left">just show the genuine sample</button>
        <p class="basis-full text-[13px] text-rose-700" data-error hidden></p></form>
      <p class="text-xs text-slate-500 mt-2">Sample: a real GST registration certificate published by the Office of the IGR Maharashtra, signed by GSTN (public document). It's used only to show the signature check.</p>
      <div id="results" class="mt-6 grid grid-cols-1 gap-4"></div></div>`;
    const out = qs('#results', view);
    const showResults = list => {
      out.className = `mt-6 grid grid-cols-1 gap-4 ${list.length > 1 ? 'md:grid-cols-2' : ''} ${list.length > 2 ? 'lg:grid-cols-3' : ''}`;
      out.innerHTML = list.map(checkCard).join('');
    };
    wireForm(qs('#check-form', view), async f => showResults((await api('/check', { method: 'POST', body: new FormData(f) })).results));
    qs('#just-sample', view).onclick = async () => showResults((await api('/check/sample')).results);
    if (new URLSearchParams(location.search).get('sample') === 'genuine') showResults((await api('/check/sample')).results);
  },
};
