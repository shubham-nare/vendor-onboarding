/* System (GET /api/v1/system, POST /system/followups, POST /system/reset): health, follow-ups, reset. */

App.views['/system'] = {
  title: 'System check',
  async render(view, note = '') {
    const d = await api('/system'), f = d.followups;
    view.innerHTML = `<div><div class="kicker">Health</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">System check</h1>
      ${note ? `<div class="mt-4 rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">${note}</div>` : ''}
      <div class="mt-6 bg-white rounded-xl border divide-y divide-slate-100 max-w-3xl">${d.checks.map(c => `<div class="p-4 flex gap-3 min-w-0">
        <span class="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white ${c.ok ? 'bg-emerald-600' : 'bg-rose-600'}">${icon(c.ok ? 'check' : 'x', 'h-3.5 w-3.5')}</span>
        <div><div class="text-sm font-medium">${esc(c.name)}</div><div class="text-xs text-slate-500 break-words">${esc(c.detail)}</div></div></div>`).join('')}</div>
      <section class="mt-8 max-w-3xl bg-white border p-4 text-sm"><div class="flex flex-wrap items-start gap-3"><div class="flex-1 min-w-0">
        <div class="font-medium">Vendor follow-ups</div>
        <div class="text-xs text-slate-500 mt-0.5">Runs by itself every ${f.every_hours} hours. Reminder after ${f.remind_after_days} days without an answer; after ${f.escalate_after_days} days a second reminder and a note to the employee who asked for the vendor.
          ${f.waiting} vendor${f.waiting === 1 ? '' : 's'} waiting now.${f.last ? ` Last follow-up sent ${esc(f.last.label)}.` : ''}</div></div>
        <button type="button" id="fu-now" class="bg-indigo-600 text-white px-4 py-2 sm:py-1.5 font-semibold">Run follow-ups now</button></div>
        <div id="fu-result" class="mt-3 border-l-4 border-l-slate-300 bg-slate-50 px-3 py-2 text-[12.5px]" hidden></div></section>
      <form id="reset-form" class="mt-8 max-w-3xl bg-white rounded-xl border p-4 flex flex-wrap items-center gap-3 text-sm">
        <div class="flex-1 basis-full sm:basis-0 min-w-0"><div class="font-medium">Reset data</div><div class="text-xs text-slate-500">Deletes every run and reloads employees, invites, vendor master, blocklist and registry records.</div></div>
        <input type="password" name="passcode" required placeholder="Passcode" aria-label="Passcode" autocomplete="off" class="flex-1 sm:flex-none min-w-0 rounded-md border px-3 py-2 sm:py-1.5">
        <button class="rounded-md bg-rose-600 text-white px-4 py-2 sm:py-1.5">Reset</button>
        <p class="basis-full text-[13px] text-rose-700" data-error hidden></p></form></div>`;
    const btn = qs('#fu-now', view), out = qs('#fu-result', view);
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await api('/system/followups', { method: 'POST' });
        out.innerHTML = `Done: <b class="tabular-nums">${r.reminders}</b> reminder${r.reminders === 1 ? '' : 's'} and <b class="tabular-nums">${r.escalations}</b> escalation${r.escalations === 1 ? '' : 's'} sent; ${r.waiting} vendor${r.waiting === 1 ? '' : 's'} waiting. ${r.reminders || r.escalations ? '' : 'Nothing was due yet.'} <a href="/outbox" class="text-indigo-700 hover:underline">Open the outbox</a>`;
      } catch (x) { out.textContent = x.message; }
      out.hidden = false; btn.disabled = false;
    };
    qs('#reset-form', view).addEventListener('submit', async e => {
      e.preventDefault();
      const f2 = e.target, err = qs('[data-error]', f2);
      if (!confirm('Delete every run and reload the reference data?')) return;
      try {
        await api('/system/reset', { method: 'POST', body: { passcode: f2.passcode.value } });
        await App.views['/system'].render(view, 'Reset done: all runs cleared, reference data reloaded.');
      } catch (x) { err.textContent = x.message; err.hidden = false; }
    });
  },
};
