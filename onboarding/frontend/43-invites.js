/* Invites (GET/POST /api/v1/invites) and pre-qualified suppliers (GET /api/v1/prequalified, POST .../request). */

App.views['/invites'] = {
  title: 'Invites',
  async render(view, created) {
    const made = new URLSearchParams(location.search).get('created');   // after the old form post
    created = created || (made ? '/apply/' + made : '');
    const d = await api('/invites');
    const bands = d.spend_bands.map(b => `<option>${esc(b)}</option>`).join('');
    const rows = d.invites.map(i => `<tr>
      <td class="px-4 py-2 font-medium sm:font-normal">${esc(i.company)}<div class="text-xs text-slate-400">${esc(i.email)}</div></td>
      <td class="px-2 py-2 text-xs" data-label="Requested by &amp; reason"><b>${esc(i.requested_by)}</b><div class="text-slate-500 line-clamp-2">${esc(i.reason)}</div></td>
      <td class="inline-sm px-2 py-2 text-xs whitespace-nowrap">${esc(i.spend_band)}${i.high_spend ? '<span class="block text-rose-700">high</span>' : ''}</td>
      <td class="inline-sm px-2 py-2">${i.application ? statusBadge(i.application.status) : `<span class="text-xs text-slate-500">${esc(i.invite_status)}</span>`}</td>
      <td class="inline-sm px-2 py-2 text-right pr-4 whitespace-nowrap">${i.link ? `<a class="text-xs text-indigo-700 underline" href="${esc(i.link)}">${esc(i.link_label)}</a>` : ''}</td></tr>`).join('');
    const link = created ? location.origin + created : '';
    view.innerHTML = `<div><div class="kicker">Requesters</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Invites</h1>
      <a href="/prequalified" data-optional class="mt-3 flex items-center justify-between gap-3 rounded-[14px] border border-slate-200 bg-white px-4 py-3 hover:border-[#0071E3]">
        <span class="text-[14px]"><b>Before inviting someone new,</b> look at the pre-qualified suppliers: already checked, ready when you need them.</span><span class="text-[#0066CC] text-[14px] font-medium shrink-0">Pre-qualified ›</span></a>
      ${link ? `<div class="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4"><div class="text-sm font-medium text-emerald-900">Invite created. In production this link is emailed to the vendor's contact.</div>
        <div class="mt-2 flex flex-wrap items-center gap-2"><input id="link" readonly class="w-full sm:w-auto sm:flex-1 min-w-0 mono text-xs rounded-md border px-2 py-1.5 bg-white" value="${esc(link)}">
          <button type="button" id="copy" class="text-xs rounded-md border bg-white px-3 py-2 sm:py-1.5">Copy</button>
          <a href="${esc(created)}" class="text-xs rounded-md bg-emerald-700 text-white px-3 py-2 sm:py-1.5">Open as the vendor →</a></div></div>` : ''}
      <div class="grid lg:grid-cols-3 gap-6 mt-6">
        <section class="bg-white rounded-xl border p-4 sm:p-5 self-start"><h2 class="text-xl">Invite a vendor</h2>
          ${d.can_invite ? '' : `<p class="mt-2 text-sm rounded-md bg-amber-50 border border-amber-200 p-3 text-amber-900">You're signed in as <b>${esc(d.actor.name)}</b> (${esc(d.actor.role_label)}). Invites are sent by the employee who needs the vendor (a requester)${d.demo ? ': switch person to Priya Nair or Rahul Desai.' : ', so their approver stays independent.'}</p>`}
          <form id="invite-form" class="mt-4 space-y-3 text-sm">
            <label class="block">Vendor company name<input name="company_name" required class="mt-1 w-full rounded-md border px-3 py-2" placeholder="As registered"></label>
            <label class="block">Vendor contact email<input name="contact_email" type="email" required class="mt-1 w-full rounded-md border px-3 py-2" placeholder="accounts@vendor.example.com"></label>
            <label class="block">Why do we need this vendor?<textarea name="business_reason" required minlength="10" rows="3" class="mt-1 w-full rounded-md border px-3 py-2" placeholder="What they'll supply, for which team, and why this vendor"></textarea></label>
            <div class="grid grid-cols-2 gap-3"><label class="block">Spend category<input name="spend_category" required class="mt-1 w-full rounded-md border px-3 py-2" placeholder="e.g. Packaging"></label>
              <label class="block">Expected yearly spend<select name="spend_band" class="mt-1 w-full rounded-md border px-2 py-2">${bands}</select></label></div>
            <p class="text-xs text-slate-500">₹50 lakh a year or more puts the vendor in the high-risk tier: the Finance controller must activate it.</p>
            <p class="text-[13px] text-rose-700" data-error hidden></p>
            <button class="w-full rounded-md bg-indigo-600 text-white py-2.5 hover:bg-indigo-700 disabled:opacity-50"${d.can_invite ? '' : ' disabled'}>Create invite link</button>
          </form></section>
        <section class="lg:col-span-2 bg-white rounded-xl border min-w-0"><h2 class="px-4 py-3 border-b text-xl">Recent invites</h2>
          <div class="overflow-x-auto"><table class="rtable w-full text-sm"><thead class="text-left text-xs text-slate-500 bg-slate-50"><tr><th class="px-4 py-2">Vendor</th><th class="px-2 py-2">Requested by &amp; reason</th><th class="px-2 py-2">Spend</th><th class="px-2 py-2">Status</th><th class="px-2 py-2"></th></tr></thead>
          <tbody class="divide-y">${rows}</tbody></table></div></section>
      </div></div>`;
    const copy = qs('#copy', view);
    if (copy) copy.onclick = () => { navigator.clipboard.writeText(qs('#link', view).value); copy.textContent = 'Copied'; };
    qs('#invite-form', view).addEventListener('submit', async e => {
      e.preventDefault();
      const f = e.target, err = qs('[data-error]', f), btn = qs('button', f);
      btn.disabled = true;
      try {
        const r = await api('/invites', { method: 'POST', body: Object.fromEntries(new FormData(f)) });
        await App.views['/invites'].render(view, r.link);
        scrollTo(0, 0);
      } catch (x) { err.textContent = x.message; err.hidden = false; btn.disabled = false; }
    });
  },
};

const RELIABILITY = { high: ['#D70015', '#FFE3E0', 'Concerns'], medium: ['#B25000', '#FFF4E5', 'Some concerns'], low: ['#248A3D', '#E9F9EE', 'Reliable'] };

App.views['/prequalified'] = {
  title: 'Pre-qualified suppliers',
  async render(view) {
    const q = new URLSearchParams(location.search).get('q') || '';
    const d = await api('/prequalified?' + new URLSearchParams({ q }));
    const bands = d.spend_bands.map(b => `<option>${esc(b)}</option>`).join('');
    const cards = d.suppliers.map(x => {
      const tone = x.reliability && RELIABILITY[x.reliability.level];
      return `<article class="bg-white border rounded-xl p-5 flex flex-col">
        <div class="flex items-start justify-between gap-3"><div class="min-w-0">
          ${x.run_id ? `<a href="/runs/${x.run_id}" class="text-[16px] font-semibold hover:text-indigo-700">${esc(x.name)}</a>` : `<span class="text-[16px] font-semibold">${esc(x.name)}</span>`}
          <div class="text-[12.5px] text-slate-500"><span class="mono">${esc(x.ref)}</span>${x.city ? ' · ' + esc(x.city) : ''}${x.state ? ', ' + esc(x.state) : ''}</div></div>
          ${tone ? `<span class="shrink-0 rounded-full px-3 py-1 text-[12px] font-semibold" style="color:${tone[0]};background:${tone[1]}" title="Reliability: ${x.reliability.score} / 100 concern">${tone[2]}</span>` : ''}</div>
        <p class="mt-3 text-[14px] text-slate-700 flex-1">${esc(x.supplies || 'No description given.')}</p>
        ${d.can_request ? `<details class="mt-4 group"><summary class="list-none inline-flex cursor-pointer rounded-full bg-indigo-600 text-white px-5 py-2 text-[13.5px] font-semibold hover:bg-indigo-700">I need this supplier</summary>
          <form data-need="${x.id}" class="mt-3 border border-l-4 border-indigo-200 border-l-indigo-600 bg-indigo-50 p-4 space-y-2">
            <label class="block text-[13px] font-semibold text-indigo-900">Why do we need them?<textarea name="business_reason" rows="2" required minlength="10" class="mt-1 w-full border bg-white px-3 py-2 text-[14px] font-normal" placeholder="e.g. Packaging for the new export line from January"></textarea></label>
            <div class="grid sm:grid-cols-2 gap-2"><label class="block text-[13px] font-semibold text-indigo-900">What for<input name="spend_category" class="mt-1 w-full border bg-white px-3 py-2 text-[14px] font-normal" value="${esc((x.supplies || '').slice(0, 60))}"></label>
              <label class="block text-[13px] font-semibold text-indigo-900">Expected spend a year<select name="spend_band" required class="mt-1 w-full border bg-white px-2 py-2 text-[14px] font-normal">${bands}</select></label></div>
            <p class="text-[12px] text-slate-600">Every check runs again on what they sent, then a reviewer approves them as an active vendor.</p>
            <p class="text-[13px] text-rose-700" data-error hidden></p>
            <button class="rounded-full bg-indigo-600 text-white px-5 py-2 text-[13.5px] font-semibold hover:bg-indigo-700">Ask for this supplier</button></form></details>` : ''}
      </article>`;
    }).join('');
    view.innerHTML = `<div class="space-y-6"><h1>Pre-qualified suppliers</h1>
      <form id="pq-search" class="flex gap-2 max-w-xl"><input name="q" value="${esc(q)}" placeholder="Search by name, what they supply, or city" aria-label="Search" class="flex-1 rounded-full border px-4 py-2 text-[14px]">
        <button class="rounded-full bg-indigo-600 text-white px-5 py-2 text-[14px] font-semibold">Search</button></form>
      ${cards ? `<div class="grid md:grid-cols-2 gap-4">${cards}</div>` : `<section class="bg-white border rounded-xl px-5 py-12 text-center">
        <p class="text-[15px] font-medium">${q ? `No supplier matches "${esc(q)}".` : 'No pre-qualified suppliers yet.'}</p>
        <p class="mt-1 text-[13px] text-slate-500">Suppliers who register for future work appear here once a reviewer adds them.</p></section>`}</div>`;
    qs('#pq-search', view).addEventListener('submit', e => {
      e.preventDefault();
      const v = new FormData(e.target).get('q');
      navigate('/prequalified' + (v ? '?' + new URLSearchParams({ q: v }) : ''));
    });
    qsa('form[data-need]', view).forEach(f => f.addEventListener('submit', async e => {
      e.preventDefault();
      const err = qs('[data-error]', f), btn = qs('button', f);
      btn.disabled = true;
      try {
        const r = await api(`/prequalified/${f.dataset.need}/request`, { method: 'POST', body: Object.fromEntries(new FormData(f)) });
        navigate(r.next);
      } catch (x) { err.textContent = x.message; err.hidden = false; btn.disabled = false; }
    }));
  },
};
