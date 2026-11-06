/* The console frame: sidebar (desktop), top bar with a scrolling menu (phones), the person switcher (demo),
   the red counts on Applications and Review, and the reminder in the corner. Drawn from GET /api/v1/session. */

const NAV = [
  ['Approvals', [['/console', 'Home'], ['/applications', 'Applications'], ['/review', 'Review'], ['/invoices', 'Invoices']]],
  ['In depth', [['/vendors', 'Vendors'], ['/prequalified', 'Pre-qualified'], ['/purchase-orders', 'Orders'], ['/audit', 'History'], ['/documents', 'Documents']]],
  ['Settings', [['/supplier-accounts', 'Accounts'], ['/outbox', 'Outbox'], ['/check', 'Checker'], ['/system', 'System']]],
];
const REVIEWER_ONLY = ['/relationships', '/purchase-orders', '/audit', '/documents', '/supplier-accounts', '/outbox', '/check', '/system'];

const isOn = (href, path) => path === href || (href !== '/console' && path.startsWith(href + '/')) ||
  (href === '/console' && path.startsWith('/invites')) || (href === '/applications' && path.startsWith('/runs/'));
const badge = (kind, n) => `<span class="review-count${kind === 'apps' ? ' apps-count' : ''}" data-count="${kind}"${n ? '' : ' hidden'} aria-label="${n} ${kind === 'apps' ? 'applications waiting' : 'waiting'}">${n > 99 ? '99+' : n}</span>`;

// Paths of switched-off features (FEATURE_* settings, from GET /api/v1/session): off the menu, and links to them are removed.
const FEATURE_PATHS = {
  payables: /^\/(bill|bills|invoices|purchase-orders|change-requests|audit)(\/|$)/,
  intel: /^\/(vendors|relationships)(\/|$)/,
  unsolicited: /^\/(apply|prequalified)$|^\/prequalified\//,
};
function featureOff(href) {
  const f = (App.session && App.session.features) || {};
  const path = new URL(href, location.href).pathname;
  return Object.entries(FEATURE_PATHS).some(([name, rx]) => !f[name] && rx.test(path));
}
// after a screen is drawn: a link into a hidden feature goes (data-optional) or turns into plain text
function dropDeadLinks(root) {
  qsa('a[href^="/"]', root).forEach(a => {
    if (!featureOff(a.getAttribute('href'))) return;
    if (a.hasAttribute('data-optional')) { a.remove(); return; }
    const span = document.createElement('span');
    span.className = a.className.split(/\s+/).filter(c => !c.startsWith('hover:') && c !== 'underline').join(' ');
    span.innerHTML = a.innerHTML;
    a.replaceWith(span);
  });
}

function navItems(session) {
  const reviewer = ['maker', 'checker'].includes(session.actor.role);
  return NAV.map(([group, items]) => [group, items.filter(([href]) => !featureOff(href) &&(reviewer || !REVIEWER_ONLY.includes(href)))]).filter(([, items]) => items.length);
}

function personaMenu(session, where, compact) {
  const a = session.actor;
  const people = session.people.map(p => `<li><button type="button" data-act-as="${p.id}" class="w-full flex items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-slate-50 ${p.id === a.id ? 'bg-indigo-50' : ''}">
      ${avatar(p, 'h-8 w-8 text-[11.5px]')}<span class="min-w-0 flex-1 leading-tight"><span class="block text-[13.5px] font-semibold truncate">${esc(p.name)}</span>
      <span class="block text-[11.5px] text-slate-500 truncate">${esc(p.role_label)} · ${esc(p.department)}</span></span>${p.id === a.id ? icon('check', 'h-4 w-4 text-indigo-600') : ''}</button></li>`).join('');
  return `<details class="persona relative min-w-0 ${compact ? '' : 'w-full'}">
    <summary class="flex items-center gap-2.5 rounded-lg text-slate-900 ${compact ? 'p-1 hover:bg-slate-100' : 'w-full border border-slate-200 bg-white hover:bg-slate-50 p-2'} select-none" aria-label="${esc(a.name)}, ${esc(a.role_label)}. Switch person">
      ${avatar(a, compact ? 'h-8 w-8 text-[11.5px]' : 'h-9 w-9 text-[12px]')}
      <span class="leading-tight text-left min-w-0 flex-1 ${compact ? 'hidden sm:block' : ''}"><span class="block text-[13.5px] font-semibold truncate">${esc(a.name)}</span><span class="block text-[11.5px] text-slate-500 truncate">${esc(a.role_label)}</span></span>
      ${icon('updown', 'h-4 w-4 text-slate-400 shrink-0')}
    </summary>
    <div class="absolute ${where} z-50 w-[23rem] max-w-[calc(100vw-2rem)] rounded-xl border border-slate-200 bg-white text-slate-900 shadow-pop overflow-hidden fade-in">
      <div class="px-4 pt-3.5 pb-3 border-b border-slate-100 bg-slate-50"><div class="text-[13px] font-semibold">Switch person</div>
        <p class="text-[12.5px] text-slate-600 mt-1 leading-snug">Logged in as <b>${esc(session.staff.name)}</b></p></div>
      <ul class="p-1.5">${people}</ul>
    </div></details>`;
}

function renderShell(session, path) {
  const groups = navItems(session), c = session.counts;
  const link = (href, label, bold) => `<a href="${href}" class="side-link ${bold ? '!font-semibold' : ''}"${isOn(href, path) ? ' aria-current="page"' : ''}>${navIcon(href)}${esc(label)}${href === '/review' ? badge('review', c.review) : href === '/applications' ? badge('apps', c.apps) : ''}</a>`;
  const side = groups.map(([group, items]) => group === 'Settings'
    ? `<details class="group/set"${items.some(([h]) => isOn(h, path)) ? ' open' : ''}><summary class="px-3 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[.08em] text-slate-500 cursor-pointer list-none flex items-center gap-1 hover:text-slate-900">Settings <span class="transition-transform group-open/set:rotate-90">›</span></summary>${items.map(([h, l]) => link(h, l)).join('')}</details>`
    : `<div class="${group === 'In depth' ? 'pt-4 border-t border-slate-200' : ''}"><div class="px-3 mb-1.5 text-[10.5px] font-semibold uppercase tracking-[.08em] text-slate-500">${group}</div>${items.map(([h, l]) => link(h, l, group === 'Approvals')).join('')}</div>`).join('');
  const who = session.demo
    ? `<div class="px-1 text-[10.5px] font-semibold uppercase tracking-[.08em] text-slate-500">Switch person</div>${personaMenu(session, 'left-0 bottom-full mb-2')}`
    : `<div class="flex items-center gap-2.5 px-1.5 py-1">${avatar(session.actor)}<span class="min-w-0 leading-tight"><span class="block text-[13px] font-semibold text-slate-900 truncate">${esc(session.actor.name)}</span><span class="block text-[11.5px] text-slate-400 truncate">${esc(session.actor.role_label)}</span></span></div>`;
  const mobile = groups.flatMap(([, items]) => items).map(([href, label]) =>
    `<a href="${href}" class="shrink-0 whitespace-nowrap inline-flex items-center gap-1.5 px-3 py-2.5 border-b-2 font-medium ${isOn(href, path) ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-900'}"${isOn(href, path) ? ' aria-current="page"' : ''}>${esc(label)}${href === '/review' ? badge('review', c.review) : href === '/applications' ? badge('apps', c.apps) : ''}</a>`).join('');
  return `
  <aside class="apple-side hidden lg:flex fixed inset-y-0 left-0 z-30 w-64 flex-col">
    <div class="h-16 px-5 flex items-center border-b border-slate-200">${brand()}</div>
    <nav class="flex-1 overflow-y-auto px-3 py-4 space-y-5" aria-label="Main">${side}</nav>
    <div class="p-3 border-t border-slate-200 space-y-2">
      <a href="/assumptions" class="side-link !py-1.5 text-[12.5px]" title="How the checks work and which sources are live">${navIcon('/help')}Help</a>
      ${who}
      <button type="button" data-logout class="side-link w-full" title="Logged in as ${esc(session.staff.name)}">${icon('logout', 'h-[18px] w-[18px]', 1.8)}Log out</button>
    </div>
  </aside>
  <header class="lg:hidden sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
    <div class="px-4 sm:px-6 h-14 flex items-center gap-3">${brand()}
      <div class="ml-auto flex items-center gap-1.5">${session.demo ? personaMenu(session, 'right-0 top-full mt-2', true) : `<span class="text-[13px] font-medium text-slate-700">${esc(session.actor.first_name)}</span>`}
        <button type="button" data-logout class="whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-slate-600 hover:bg-slate-100">Log out</button></div>
    </div>
    <nav id="mainnav" class="px-2 sm:px-4 flex flex-nowrap overflow-x-auto no-scrollbar fade-r text-[13.5px]" aria-label="Main">${mobile}</nav>
  </header>
  <div class="lg:pl-64"><main id="view" class="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-10 2xl:px-12 py-6 sm:py-8"></main></div>
  <aside id="pending-note" hidden role="status" aria-live="polite" class="bg-white border border-amber-300 border-l-4 border-l-amber-500 text-[13px]">
    <div class="flex items-start gap-3 px-4 py-3"><div class="flex-1 min-w-0">
      <div class="font-bold text-amber-800"><span id="pending-n" class="tabular-nums"></span> still waiting for you</div>
      <ul id="pending-list" class="mt-1.5 space-y-1 text-[12.5px] text-slate-700"></ul>
      <a href="/review" class="mt-2 inline-block text-[12.5px] font-semibold text-indigo-700 hover:underline">Open Review</a></div>
      <button type="button" id="pending-x" class="text-slate-400 hover:text-slate-700 px-1" aria-label="Hide for this session">✕</button></div>
  </aside>`;
}

// the red counts: drawn with the frame, refreshed every minute and when the tab comes back
function paintCounts(c) {
  qsa('[data-count]').forEach(b => {
    const n = b.dataset.count === 'apps' ? c.apps : c.review;
    b.textContent = n > 99 ? '99+' : n; b.hidden = !n;
    b.setAttribute('aria-label', `${n} ${b.dataset.count === 'apps' ? 'applications waiting' : 'waiting'}`);
  });
}
let reminded = false;
function remind(d, path) {
  const box = qs('#pending-note');
  if (reminded || !box || !d.count || path === '/console' || path.startsWith('/runs/') || store.get('pending-hidden')) return;
  reminded = true;
  qs('#pending-n').textContent = d.count;
  qs('#pending-list').innerHTML = d.items.map(t => `<li><a class="hover:underline" href="${esc(t.href)}">${esc(t.verb)}: ${esc(t.name)} (${esc(t.ref)})</a></li>`).join('')
    + (d.count > d.items.length ? `<li class="text-slate-500">and ${d.count - d.items.length} more</li>` : '');
  box.hidden = false;
  qs('#pending-x').onclick = () => { box.hidden = true; store.set('pending-hidden', '1'); };
}
async function refreshCounts() {
  try { const d = await api('/console/pending'); paintCounts(d); remind(d, location.pathname); } catch (e) { /* try again next minute */ }
}

function wireShell() {
  document.addEventListener('click', async e => {
    const act = e.target.closest('[data-act-as]');
    if (act) {
      await api('/session/actor', { method: 'POST', body: { employee_id: Number(act.dataset.actAs) } });
      return boot();
    }
    if (e.target.closest('[data-logout]')) {
      const r = await api('/session/logout', { method: 'POST' });
      location.href = r.next || '/';
      return;
    }
    qsa('details.persona[open]').forEach(d => { if (!d.contains(e.target)) d.open = false; });
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') qsa('details.persona[open]').forEach(d => { d.open = false; }); });
  setInterval(() => { if (!document.hidden) refreshCounts(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshCounts(); });
}
