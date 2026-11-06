/* Parakh Vendor Onboarding */
(()=>{'use strict';
const App = { session: null, views: {} };
class ApiError extends Error {
constructor(status, message) { super(message); this.status = status; }
}
async function api(path, { method = 'GET', body } = {}) {
const opts = { method, credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
if (body instanceof FormData) opts.body = body;
else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
let r;
try { r = await fetch('/api/v1' + path, opts); }
catch (e) { throw new ApiError(0, 'Could not reach the server. Check your connection and try again.'); }
let data = null;
try { data = await r.json(); } catch (e) { /* an empty or broken answer */ }
if (r.status === 401) {
location.href = '/company/login?next=' + encodeURIComponent(location.pathname + location.search);
throw new ApiError(401, (data && data.error) || 'Please log in.');
}
if (!r.ok) throw new ApiError(r.status, (data && data.error) || `Something went wrong (${r.status}).`);
return data;
}
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];
const inr = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const store = {
get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
const ICONS = {
check: '<path d="M5 12.5l4.2 4.2L19 7"/>',
arrow: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
chev: '<path d="m9 18 6-6-6-6"/>',
x: '<path d="M18 6 6 18M6 6l12 12"/>',
send: '<path d="M21.5 2.5 11 13"/><path d="M21.5 2.5 15 21l-4-8-8-4z"/>',
logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
updown: '<path d="m7 15 5 5 5-5M7 9l5-5 5 5"/>',
};
const icon = (name, cls = 'h-4 w-4', width = 2) =>
`<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
const NAV_ICONS = {
'/console': '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
'/applications': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
'/review': '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>',
'/invoices': '<path d="M5 3h14v18l-2.3-1.5L14.3 21 12 19.5 9.7 21l-2.4-1.5L5 21z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
'/vendors': '<path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/><path d="M16 9h2a2 2 0 0 1 2 2v10"/><path d="M3 21h18M8 7h4M8 11h4M8 15h4"/>',
'/prequalified': '<circle cx="12" cy="8" r="5"/><path d="M8.5 12.5 7 22l5-3 5 3-1.5-9.5"/>',
'/purchase-orders': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h5"/>',
'/audit': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
'/documents': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
'/supplier-accounts': '<circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 12 0v1"/><path d="M16 11h6M19 8v6"/>',
'/outbox': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6 8.5-6"/>',
'/check': '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="11.5" cy="11.5" r="3.5"/><path d="m14 14 3 3"/>',
'/system': '<path d="M22 12h-4l-3 8L9 4l-3 8H2"/>',
'/help': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/><path d="M12 17h.01"/>',
};
const navIcon = href => `<svg class="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${NAV_ICONS[href] || ''}</svg>`;
const STATUS = {
APPROVED: ['Approved', 'text-emerald-700 bg-emerald-50'], ACTIVE: ['Active vendor', 'text-emerald-800 !bg-emerald-100'],
PENDING_VENDOR: ['Pending: vendor to fix', 'text-amber-700 bg-amber-50'], PENDING_REVIEW: ['Pending: internal review', 'text-amber-700 bg-amber-50'],
IN_PROGRESS: ['In progress', 'text-amber-700 bg-amber-50'], '': ['Running', 'text-amber-700 bg-amber-50'],
REJECTED: ['Rejected', 'text-rose-700 bg-rose-50'], PREQUALIFIED: ['Pre-qualified', 'text-sky-700 bg-sky-50'],
};
const statusBadge = st => { const [label, c] = STATUS[st] || [st, 'text-slate-500 bg-slate-50']; return `<span class="tag dot ${c}">${esc(label)}</span>`; };
const tierChip = tier => {
if (!tier) return '';
const c = { low: 'text-emerald-700', medium: 'text-amber-700', high: 'text-rose-700' }[tier] || 'text-slate-500';
return `<span class="inline-flex items-center gap-1.5 text-xs whitespace-nowrap ${c}"><span class="h-2 w-2 rounded-full bg-current"></span>${esc(tier)} risk</span>`;
};
const TONES = ['bg-indigo-100 text-indigo-700', 'bg-emerald-100 text-emerald-700', 'bg-amber-100 text-amber-800', 'bg-rose-100 text-rose-700', 'bg-violet-100 text-violet-700', 'bg-sky-100 text-sky-700'];
const monogram = (name, size = 'h-9 w-9 text-[12px]') => {
const w = String(name || '?').split(/\s+/).filter(Boolean), tone = [...String(name || '')].reduce((a, c) => a + c.charCodeAt(0), 0) % 6;
return `<span class="${size} ${TONES[tone]} shrink-0 inline-flex items-center justify-center rounded-lg font-semibold" aria-hidden="true">${esc((w[0] || '?')[0])}${esc(w[1] ? w[1][0] : '')}</span>`;
};
const ROLE_TONE = { sponsor: 'bg-amber-100 text-amber-800', maker: 'bg-indigo-100 text-indigo-700', checker: 'bg-emerald-100 text-emerald-700' };
const avatar = (p, size = 'h-8 w-8 text-[11.5px]') => {
const w = p.name.split(/\s+/);
return `<span class="${size} ${ROLE_TONE[p.role] || 'bg-slate-100 text-slate-700'} shrink-0 inline-flex items-center justify-center rounded-full font-semibold" aria-hidden="true">${esc(w[0][0])}${esc(w[w.length - 1][0])}</span>`;
};
let brandSeq = 0;
const brand = () => {
const id = 'bw-app-' + (++brandSeq);
const word = '<tspan class="bw-cap">P</tspan>arakh';
return `<a href="/" title="Home" aria-label="Parakh Vendor Onboarding, home" class="brand-word shrink-0" data-full>
<svg viewBox="0 0 170 64" width="118" height="44" aria-hidden="true">
<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3EDE70"/><stop offset=".45" stop-color="#248B3E"/><stop offset="1" stop-color="#12642F"/></linearGradient></defs>
<text x="85" y="47" text-anchor="middle" class="bw-text" fill="url(#${id})" stroke="url(#${id})">${word}</text>
<text x="84.6" y="46.4" text-anchor="middle" class="bw-text bw-rim" fill="none" stroke="#fff">${word}</text>
</svg></a>`;
};
function mountSky(pale) {
if (qs('#sky')) return;
const sky = document.createElement('div');
sky.className = 'sky'; sky.id = 'sky'; sky.setAttribute('aria-hidden', 'true');
if (pale) sky.style.background = 'linear-gradient(180deg, #BBD6F8 0%, #D6E7FB 38%, #E7F0FB 70%, #F1F4F9 100%)';
const clouds = [[9, 220, 54, 140, -30, .75], [26, 160, 40, 170, -110, .6], [58, 260, 60, 190, -70, .55], [80, 180, 44, 155, -140, .6]];
sky.innerHTML = '<div class="sky-glow"></div><div class="sky-far">' + clouds.map(([top, w, h, dur, delay, op]) =>
`<div class="cloud" style="top:${top}%;width:${w}px;height:${h}px;animation-duration:${dur}s;animation-delay:${delay}s;opacity:${op}"></div>`).join('') + '</div>';
document.body.prepend(sky);
if (calm) return;
let raf = 0, ev = null;
addEventListener('pointermove', e => {
ev = e;
if (raf) return;
raf = requestAnimationFrame(() => {
raf = 0;
sky.style.setProperty('--mx', (ev.clientX / innerWidth * 2 - 1).toFixed(3));
sky.style.setProperty('--my', (ev.clientY / innerHeight * 2 - 1).toFixed(3));
sky.style.setProperty('--cx', ev.clientX + 'px');
sky.style.setProperty('--cy', ev.clientY + 'px');
});
}, { passive: true });
}
const NAV = [
['Approvals', [['/console', 'Home'], ['/applications', 'Applications'], ['/review', 'Review'], ['/invoices', 'Invoices']]],
['In depth', [['/vendors', 'Vendors'], ['/prequalified', 'Pre-qualified'], ['/purchase-orders', 'Orders'], ['/audit', 'History'], ['/documents', 'Documents']]],
['Settings', [['/supplier-accounts', 'Accounts'], ['/outbox', 'Outbox'], ['/check', 'Checker'], ['/system', 'System']]],
];
const REVIEWER_ONLY = ['/relationships', '/purchase-orders', '/audit', '/documents', '/supplier-accounts', '/outbox', '/check', '/system'];
const isOn = (href, path) => path === href || (href !== '/console' && path.startsWith(href + '/')) ||
(href === '/console' && path.startsWith('/invites')) || (href === '/applications' && path.startsWith('/runs/'));
const badge = (kind, n) => `<span class="review-count${kind === 'apps' ? ' apps-count' : ''}" data-count="${kind}"${n ? '' : ' hidden'} aria-label="${n} ${kind === 'apps' ? 'applications waiting' : 'waiting'}">${n > 99 ? '99+' : n}</span>`;
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
const STAR_PATH = 'M100.0 6.0 L103.3 6.3 L106.5 7.4 L109.6 9.0 L112.5 11.2 L115.2 13.8 L117.7 16.8 L119.9 20.1 L122.0 23.4 L123.8 26.8 L125.5 30.0 L127.1 33.0 L128.7 35.6 L130.3 37.9 L132.1 39.7 L134.0 41.1 L136.2 42.1 L138.7 42.7 L141.4 43.0 L144.5 43.0 L147.9 42.9 L151.5 42.8 L155.3 42.7 L159.2 42.8 L163.2 43.1 L167.0 43.8 L170.7 44.8 L174.0 46.2 L177.0 48.1 L179.5 50.3 L181.4 53.0 L182.7 56.0 L183.5 59.3 L183.6 62.8 L183.2 66.4 L182.2 70.1 L180.9 73.7 L179.2 77.3 L177.3 80.7 L175.3 84.0 L173.4 87.1 L171.6 89.9 L170.1 92.6 L169.0 95.2 L168.2 97.6 L168.0 100.0 L168.2 102.4 L169.0 104.8 L170.1 107.4 L171.6 110.1 L173.4 112.9 L175.3 116.0 L177.3 119.3 L179.2 122.7 L180.9 126.3 L182.2 129.9 L183.2 133.6 L183.6 137.2 L183.5 140.7 L182.7 144.0 L181.4 147.0 L179.5 149.7 L177.0 151.9 L174.0 153.8 L170.7 155.2 L167.0 156.2 L163.2 156.9 L159.2 157.2 L155.3 157.3 L151.5 157.2 L147.9 157.1 L144.5 157.0 L141.4 157.0 L138.7 157.3 L136.2 157.9 L134.0 158.9 L132.1 160.3 L130.3 162.1 L128.7 164.4 L127.1 167.0 L125.5 170.0 L123.8 173.2 L122.0 176.6 L119.9 179.9 L117.7 183.2 L115.2 186.2 L112.5 188.8 L109.6 191.0 L106.5 192.6 L103.3 193.7 L100.0 194.0 L96.7 193.7 L93.5 192.6 L90.4 191.0 L87.5 188.8 L84.8 186.2 L82.3 183.2 L80.1 179.9 L78.0 176.6 L76.2 173.2 L74.5 170.0 L72.9 167.0 L71.3 164.4 L69.7 162.1 L67.9 160.3 L66.0 158.9 L63.8 157.9 L61.3 157.3 L58.6 157.0 L55.5 157.0 L52.1 157.1 L48.5 157.2 L44.7 157.3 L40.8 157.2 L36.8 156.9 L33.0 156.2 L29.3 155.2 L26.0 153.8 L23.0 151.9 L20.5 149.7 L18.6 147.0 L17.3 144.0 L16.5 140.7 L16.4 137.2 L16.8 133.6 L17.8 129.9 L19.1 126.3 L20.8 122.7 L22.7 119.3 L24.7 116.0 L26.6 112.9 L28.4 110.1 L29.9 107.4 L31.0 104.8 L31.8 102.4 L32.0 100.0 L31.8 97.6 L31.0 95.2 L29.9 92.6 L28.4 89.9 L26.6 87.1 L24.7 84.0 L22.7 80.7 L20.8 77.3 L19.1 73.7 L17.8 70.1 L16.8 66.4 L16.4 62.8 L16.5 59.3 L17.3 56.0 L18.6 53.0 L20.5 50.3 L23.0 48.1 L26.0 46.2 L29.3 44.8 L33.0 43.8 L36.8 43.1 L40.8 42.8 L44.7 42.7 L48.5 42.8 L52.1 42.9 L55.5 43.0 L58.6 43.0 L61.3 42.7 L63.8 42.1 L66.0 41.1 L67.9 39.7 L69.7 37.9 L71.3 35.6 L72.9 33.0 L74.5 30.0 L76.2 26.8 L78.0 23.4 L80.1 20.1 L82.3 16.8 L84.8 13.8 L87.5 11.2 L90.4 9.0 L93.5 7.4 L96.7 6.3Z';
function starTile(s, i) {
const n = s.count, note = s.amount !== undefined ? (n ? `${inr(s.amount)} ${s.note}` : '') : s.note;
return `<a href="${esc(s.href)}" class="star-tile ${n ? 'star-wait' : 'star-clear'}" draggable="false" title="Spin me, or throw me">
<svg viewBox="0 0 200 200" aria-hidden="true"><defs><linearGradient id="starfill${i}" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="${n ? '#E3EEFF' : '#F0F5FC'}"/><stop offset="1" stop-color="${n ? '#C9DFFF' : '#E1EBF8'}"/></linearGradient></defs>
<path d="${STAR_PATH}" fill="url(#starfill${i})"/></svg>
<span class="star-body">
<span class="block text-[13px] font-semibold text-slate-700 leading-tight">${esc(s.label)}</span>
<span class="block mt-1 text-[42px] font-semibold tracking-tight leading-none tabular-nums ${n ? 'text-[#0071E3]' : 'text-[#6E8DB8]'}">${n}</span>
<span class="block mt-1 text-[11.5px] leading-snug text-slate-600">${n ? esc(note) : 'All clear'}</span>
</span></a>`;
}
function todoRow(t) {
const tag = ['BILL', 'CHANGE'].includes(t.status)
? `<span class="tag ${t.status === 'CHANGE' ? 'text-rose-700' : 'text-amber-700'}">${esc(t.detail)}${t.amount ? ' · ' + inr(t.amount) : ''}</span>`
: statusBadge(t.status);
return `<li><a href="${esc(t.href)}" class="group flex items-center gap-3 px-4 sm:px-5 py-3 hover:bg-slate-50">
${monogram(t.name)}
<span class="flex-1 min-w-0"><span class="block text-[14px] font-medium truncate">${esc(t.name)}</span>
<span class="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px] text-slate-500">
<span class="mono">${esc(t.ref)}</span>${tag}${t.fraud ? '<span class="tag text-rose-700">fraud class</span>' : ''}${tierChip(t.risk)}
${t.waiting ? `<span class="text-slate-400">${esc(t.waiting)}</span>` : ''}</span></span>
<span class="hidden sm:inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white group-hover:bg-indigo-700">${esc(t.verb)} ${icon('chev', 'h-3.5 w-3.5')}</span>
<span class="sm:hidden text-slate-400">${icon('chev')}</span></a></li>`;
}
function chasingRow(w) {
const red = w.tone === 'red';
const so_far = `Asked ${esc(w.asked)}${w.reminded ? ` · reminded ${esc(w.reminded)}` : ''}${w.escalated ? ` · <b class="text-rose-700">sent to ${esc(w.requester || 'the requester')} ${esc(w.escalated)}</b>` : ''}`;
return `<tr class="border-l-4 ${red ? 'border-l-rose-600 bg-rose-50' : 'border-l-amber-500'}">
<td class="px-4 sm:px-5 py-2.5"><a href="/runs/${w.run_id}" class="font-medium hover:underline">${esc(w.name)}</a>
<div class="text-[11.5px] text-slate-500"><span class="mono">${esc(w.ref)}</span>${w.requester ? ` · asked for by ${esc(w.requester)}` : ''}</div></td>
<td class="px-3 py-2.5 text-center tabular-nums font-bold text-[15px] ${red ? 'text-rose-700' : 'text-amber-700'}">${w.days}</td>
<td class="px-3 py-2.5 hidden md:table-cell text-[12px] text-slate-600">${so_far}</td>
<td class="px-3 py-2.5 hidden sm:table-cell text-[12px] text-slate-600">${w.next ? `${esc(w.next.what)} on ${esc(w.next.on)}` : 'Waiting for the vendor to resubmit'}</td></tr>`;
}
App.views['/console'] = {
title: 'Home',
async render(view) {
const d = await api('/console/home');
paintCounts(d.counts);
const req = d.requester, todo = d.todo;
view.innerHTML = `<div class="space-y-6">
<h1>Welcome back, ${esc(d.actor.first_name)}</h1>
<a href="/invites" id="invite-box" class="group block rounded-[18px] bg-[#0071E3] text-white px-6 sm:px-8 py-7 sm:py-8 hover:bg-[#0077ED] transition">
<div class="flex flex-wrap items-center gap-5">
<span class="h-14 w-14 shrink-0 rounded-full bg-white/15 grid place-items-center">${icon('send', 'h-7 w-7', 1.8)}</span>
<span class="flex-1 min-w-[14rem]"><span class="block text-[26px] sm:text-[30px] font-semibold tracking-tight leading-tight">${req ? 'Invite a vendor' : 'Invites'}</span>
<span class="block mt-1 text-[15px] text-white/85">${req ? 'Send a registration link. We check everything they submit.' : 'Every registration link sent, and who has yet to register.'}
${d.open_invites ? `<b class="text-white">${d.open_invites} open.</b>` : ''}</span></span>
<span class="inline-flex items-center gap-1.5 rounded-full bg-white text-[#0071E3] px-5 py-2.5 text-[14px] font-semibold group-hover:bg-white/90">${req ? 'Invite' : 'Open'} ${icon('chev', 'h-4 w-4')}</span>
</div></a>
<div class="flex flex-wrap justify-evenly gap-x-10 gap-y-6 py-2" id="stars">${d.stars.map(starTile).join('')}</div>
<section class="bg-white border rounded-xl min-w-0">
<div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Waiting for you ${todo.length ? `<span class="ml-1.5 inline-flex items-center justify-center rounded-full bg-amber-500 text-white text-[11.5px] font-semibold h-5 min-w-[20px] px-1.5 align-middle">${todo.length}</span>` : ''}</h2></div>
${todo.length ? `<ul class="divide-y divide-slate-100">${todo.slice(0, 5).map(todoRow).join('')}</ul>
${todo.length > 5 ? `<a href="/review" class="block border-t border-slate-100 px-4 sm:px-5 py-3 text-[13.5px] font-medium text-indigo-700 hover:bg-slate-50">See all ${todo.length} in Review ›</a>` : ''}`
: `<div class="px-5 py-12 text-center"><span class="mx-auto h-11 w-11 rounded-full bg-emerald-50 text-emerald-600 grid place-items-center">${icon('check', 'h-5 w-5')}</span><p class="mt-3 text-[14px] font-medium">You're all caught up</p></div>`}
</section>
${d.chasing.length ? `<section class="bg-white border rounded-xl min-w-0" id="chasing">
<div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Waiting on vendors <span class="ml-1.5 inline-flex items-center justify-center bg-amber-500 text-white text-[11.5px] font-semibold h-5 min-w-[20px] px-1.5 align-middle">${d.chasing.length}</span></h2></div>
<table class="w-full text-[13px]"><thead class="bg-slate-50 text-[11.5px] uppercase tracking-wide text-slate-500"><tr>
<th class="text-left font-semibold px-4 sm:px-5 py-2">Vendor</th><th class="font-semibold px-3 py-2 text-center">Days waiting</th>
<th class="text-left font-semibold px-3 py-2 hidden md:table-cell">Chased so far</th><th class="text-left font-semibold px-3 py-2 hidden sm:table-cell">Next</th></tr></thead>
<tbody class="divide-y divide-slate-100">${d.chasing.map(chasingRow).join('')}</tbody></table></section>` : ''}
${d.scenarios.length ? `<details class="bg-white rounded-xl border overflow-hidden"><summary class="px-4 sm:px-5 py-3 cursor-pointer text-[14px] font-medium">Try a scenario</summary>
<ol class="grid md:grid-cols-2 xl:grid-cols-3 p-1.5 border-t border-slate-100">${d.scenarios.map(sc => `<li><a href="/demo/${esc(sc.key)}" class="group flex items-start gap-3 rounded-lg px-3 py-2.5 h-full hover:bg-slate-50">
<span class="flex-1 min-w-0"><span class="block text-[13.5px] font-medium leading-snug group-hover:text-indigo-700">${esc(sc.title)}</span>
<span class="mt-1.5 flex flex-wrap items-center gap-2">${statusBadge(sc.expected)}</span></span></a></li>`).join('')}</ol></details>` : ''}
</div>`;
return startStars(qsa('.star-tile', view));
},
};
function sparkles(x, y) {
for (let k = 0; k < 14; k++) {
const el = document.createElement('span'), a = Math.random() * Math.PI * 2, d = 40 + Math.random() * 90;
el.className = 'sparkle'; el.style.left = x + 'px'; el.style.top = y + 'px';
document.body.appendChild(el);
el.animate([{ transform: 'translate(0,0) scale(.4)', opacity: 1 },
{ transform: `translate(${Math.cos(a) * d}px, ${Math.sin(a) * d}px) scale(${.6 + Math.random()})`, opacity: 0 }],
{ duration: 700 + Math.random() * 700, delay: Math.random() * 500, easing: 'cubic-bezier(.2,.7,.3,1)' }).onfinish = () => el.remove();
}
}
function startStars(tiles) {
const stars = tiles.map((tile, i) => {
const base = calm ? 0 : (i % 2 ? -1 : 1) * (6 + i);
return { tile, svg: tile.querySelector('svg'), base, vel: base, angle: i * 25, drag: null, moved: false, flying: false };
});
const angleAt = (s, e) => { const r = s.tile.getBoundingClientRect(); return Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI; };
const launch = (s, ux, uy) => {
if (s.flying || calm) return;
s.flying = true; s.tile.classList.add('flying');
s.vel = Math.sign(s.vel || 1) * 900;
const r = s.tile.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2, M = 70;
const reach = [ux > 0 ? (innerWidth - M - cx) / ux : ux < 0 ? (M - cx) / ux : Infinity,
uy > 0 ? (innerHeight - M - cy) / uy : uy < 0 ? (M - cy) / uy : Infinity];
const dist = Math.max(80, Math.min(...reach)), dx = ux * dist, dy = uy * dist;
const fly = s.tile.animate([
{ transform: 'translate(0, 0) scale(1)', offset: 0, easing: 'cubic-bezier(.15,.75,.3,1)' },
{ transform: `translate(${dx}px, ${dy}px) scale(.32)`, offset: .3 },
{ transform: `translate(${dx * 1.03}px, ${dy * 1.03}px) scale(.36)`, offset: .62, easing: 'cubic-bezier(.55,0,.8,.3)' },
{ transform: `translate(${-ux * 16}px, ${-uy * 16}px) scale(1.06)`, offset: .86 },
{ transform: 'translate(0, 0) scale(1)', offset: 1 }], { duration: 2800 });
setTimeout(() => sparkles(cx + dx, cy + dy), 850);
setTimeout(() => sparkles(cx + dx, cy + dy), 1450);
fly.onfinish = () => { s.flying = false; s.tile.classList.remove('flying'); };
};
stars.forEach(s => {
s.tile.addEventListener('dragstart', e => e.preventDefault());
s.tile.addEventListener('pointerdown', e => {
if (s.flying || e.button !== 0) return;
s.tile.setPointerCapture(e.pointerId);
s.drag = { a: angleAt(s, e), t: performance.now(), x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, vx: 0, vy: 0 };
s.moved = false; s.tile.classList.add('held');
});
s.tile.addEventListener('pointermove', e => {
const d = s.drag; if (!d) return;
const now = performance.now(), dt = Math.max(.008, (now - d.t) / 1000), a = angleAt(s, e);
let da = a - d.a; if (da > 180) da -= 360; if (da < -180) da += 360;
s.angle += da;
s.vel = s.vel * .5 + (da / dt) * .5;
d.vx = d.vx * .5 + ((e.clientX - d.x) / dt) * .5;
d.vy = d.vy * .5 + ((e.clientY - d.y) / dt) * .5;
if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) > 6) s.moved = true;
Object.assign(d, { a, t: now, x: e.clientX, y: e.clientY });
});
const release = () => {
const d = s.drag; if (!d) return;
s.drag = null; s.tile.classList.remove('held');
const speed = Math.hypot(d.vx, d.vy);
if (s.moved && speed > 900) launch(s, d.vx / speed, d.vy / speed);
else if (s.moved && Math.abs(s.vel) > 1100) { const a = Math.random() * Math.PI * 2; launch(s, Math.cos(a), Math.sin(a)); }
};
s.tile.addEventListener('pointerup', release);
s.tile.addEventListener('pointercancel', release);
s.tile.addEventListener('click', e => { if (s.moved || s.flying) { e.preventDefault(); e.stopPropagation(); s.moved = false; } }, true);
});
let last = performance.now(), running = true;
const frame = now => {
if (!running) return;
const dt = Math.min(.05, (now - last) / 1000); last = now;
for (const s of stars) {
if (!s.drag) { s.vel += (s.base - s.vel) * (1 - Math.exp(-dt * (s.flying ? .4 : 1.1))); s.angle += s.vel * dt; }
s.svg.style.transform = `rotate(${s.angle.toFixed(2)}deg)`;
}
requestAnimationFrame(frame);
};
requestAnimationFrame(frame);
return () => { running = false; };
}
const emptyState = (title, text) => `<div class="px-5 py-10 text-center">
<span class="mx-auto h-11 w-11 rounded-full bg-slate-100 text-slate-500 grid place-items-center">${icon('check', 'h-5 w-5')}</span>
<p class="mt-3 text-[14px] font-medium text-slate-800">${esc(title)}</p><p class="mt-1 text-[12.5px] text-slate-500 max-w-sm mx-auto">${esc(text)}</p></div>`;
document.addEventListener('click', e => {
const row = e.target.closest('tr[data-href]');
if (!row || e.target.closest('a, button, input, select')) return;
navigate(row.dataset.href);
});
const APP_STATUSES = [['', 'Any status'], ['PENDING_REVIEW', 'Internal review'], ['PENDING_VENDOR', 'Vendor to fix'], ['APPROVED', 'Approved'], ['ACTIVE', 'Active'], ['PREQUALIFIED', 'Pre-qualified'], ['REJECTED', 'Rejected']];
App.views['/applications'] = {
title: 'Applications',
async render(view) {
const params = new URLSearchParams(location.search), status = params.get('status') || '', q = params.get('q') || '';
const d = await api('/applications?' + new URLSearchParams({ status, q }));
paintCounts(d.counts);
const rows = d.applications.map(x => `<tr class="group hover:bg-slate-50/80 ${x.run_id ? 'cursor-pointer' : ''} ${x.waiting ? 'bg-rose-50/40' : ''}"${x.run_id ? ` data-href="/runs/${x.run_id}"` : ''}>
<td class="pl-5 pr-2 py-3">${x.run_id ? `<a href="/runs/${x.run_id}" class="mono font-medium group-hover:text-indigo-700">${esc(x.ref)}</a>` : `<span class="mono font-medium">${esc(x.ref)}</span>`}
${x.waiting ? '<span class="ml-1 inline-flex items-center rounded-full bg-[#FF3B30] text-white text-[10.5px] font-semibold px-2 py-0.5 align-middle">Waiting for you</span>' : ''}
<div class="text-[11.5px] text-slate-500">${esc(x.name)}</div></td>
<td class="px-2 py-3" data-label="Vendor">${x.vendor ? `<a class="hover:text-indigo-700" href="/vendors/${esc(x.vendor.id)}">${esc(x.vendor.name)}</a><div class="text-[11.5px] text-slate-500 mono">${esc(x.vendor.id)}</div>` : '—'}</td>
<td class="px-2 py-3" data-label="Status">${statusBadge(x.status)}</td>
<td class="px-2 py-3" data-label="Risk">${x.risk ? tierChip(x.risk) : '—'}</td>
<td class="px-2 py-3 text-slate-600" data-label="Came in through">${esc(x.came_in)}</td>
<td class="pr-5 pl-2 py-3 text-slate-500 whitespace-nowrap" data-label="Submitted">${esc(x.submitted.label)}</td></tr>`).join('');
view.innerHTML = `<div class="space-y-5">
<div class="flex flex-wrap items-end justify-between gap-4"><h1>Applications</h1>
<form id="app-filter" class="flex gap-2 w-full sm:w-auto">
<select name="status" class="rounded-lg border px-2 py-2 text-[13px]" aria-label="Status">${APP_STATUSES.map(([k, l]) => `<option value="${k}"${k === status ? ' selected' : ''}>${l}</option>`).join('')}</select>
<input name="q" value="${esc(q)}" type="search" placeholder="VOB-number, name or GSTIN" aria-label="Search applications" class="w-full sm:w-64 rounded-lg border px-3 py-2 text-[13px]">
<button class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-[13px] font-medium hover:bg-slate-50">Filter</button>
</form></div>
<section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]">
<thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">Application</th><th class="px-2">Vendor</th><th class="px-2">Status</th><th class="px-2">Risk</th><th class="px-2">Came in through</th><th class="pr-5 pl-2">Submitted</th></tr></thead>
<tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>`
: emptyState(status || q ? 'No applications match' : 'No applications yet', status || q ? 'Try another filter.' : 'Applications arrive through invites and the supplier portal.')}</section>
</div>`;
qs('#app-filter', view).addEventListener('submit', e => {
e.preventDefault();
const f = new FormData(e.target), p = new URLSearchParams();
if (f.get('status')) p.set('status', f.get('status'));
if (f.get('q')) p.set('q', f.get('q'));
navigate('/applications' + (p.toString() ? '?' + p : ''));
});
},
};
const reviewRow = (t, full) => `<li><a href="${esc(t.href)}" class="group flex flex-wrap items-center gap-3 px-4 sm:px-5 py-3 hover:bg-slate-50">
${monogram(t.name)}
<span class="flex-1 min-w-[14rem]"><span class="block text-[14px] font-medium group-hover:text-indigo-700">${esc(t.name)}</span>
<span class="block text-[12px] text-slate-500"><span class="mono">${esc(t.ref)}</span>${t.detail ? ' · ' + esc(t.detail) : ''}${t.amount ? ' · ' + inr(t.amount) : ''}${t.waiting ? ' · ' + esc(t.waiting) : ''}</span></span>
${['BILL', 'CHANGE'].includes(t.status) ? '' : statusBadge(t.status)}${full ? tierChip(t.risk) : ''}
<span class="hidden sm:inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-[12.5px] font-semibold text-white group-hover:bg-indigo-700">${esc(t.verb)} ${icon('chev', 'h-3.5 w-3.5')}</span></a></li>`;
function changeItem(c) {
const req = Object.entries(c.requested).map(([k, v]) => `<span class="mr-3"><span class="text-slate-500">${esc(k)}:</span> <span class="mono">${esc(v)}</span></span>`).join('');
return `<li class="px-4 sm:px-5 py-3.5" data-change="${c.id}">
<div class="flex flex-wrap items-center gap-2"><span class="tag ${c.kind === 'bank_account' ? 'text-rose-700' : 'text-slate-600'}">${c.kind === 'bank_account' ? 'bank account change' : 'contact change'}</span>
${c.vendor_id ? `<a class="font-medium hover:text-indigo-700" href="/vendors/${esc(c.vendor_id)}">${esc(c.name)}</a>` : `<span class="font-medium">${esc(c.name)}</span>`}
<span class="text-[12px] text-slate-500">${esc(c.created.label)}</span></div>
<div class="mt-1 text-[13px] text-slate-700">${req}${c.reason ? `<div class="text-slate-500">Reason given: ${esc(c.reason)}</div>` : ''}
${c.document ? `<a class="text-indigo-700 hover:underline" target="_blank" rel="noopener" href="/files/${esc(c.document.sha256)}">${esc(c.document.name)}</a>` : ''}</div>
${c.mine ? `<form class="mt-2 flex flex-wrap gap-2" data-decide="${c.id}">
<input name="note" required minlength="5" placeholder="How you checked it" class="flex-1 min-w-[14rem] rounded-md border px-3 py-1.5 text-[13px]">
<button name="decision" value="approve" class="rounded-md bg-indigo-600 text-white px-3 py-1.5 text-[13px] font-semibold hover:bg-indigo-700">Approve</button>
<button name="decision" value="reject" class="rounded-md border border-rose-300 bg-white text-rose-700 px-3 py-1.5 text-[13px] font-semibold hover:bg-rose-50">Reject</button>
<p class="w-full text-[12.5px] text-rose-700" data-error hidden></p></form>`
: '<p class="mt-1.5 text-[12px] text-slate-500">Bank-account changes are decided by the Finance controller.</p>'}</li>`;
}
App.views['/review'] = {
title: 'Review',
async render(view) {
const d = await api('/review');
paintCounts(d.counts);
const list = (items, none) => items.length ? `<ul class="divide-y divide-slate-100">${items.map(t => reviewRow(t, d.full)).join('')}</ul>` : `<p class="px-5 py-4 text-[13px] text-slate-500">${none}</p>`;
view.innerHTML = `<div class="space-y-6"><h1>Review</h1>
${d.full && d.changes.length ? `<section id="changes" class="bg-white border rounded-xl overflow-hidden">
<div class="px-4 sm:px-5 py-4 border-b border-slate-100"><h2 class="text-[16px]">Change requests <span class="text-slate-400 font-normal">${d.changes.length}</span></h2>
<p class="text-[12.5px] text-slate-500 mt-0.5">Approve a new bank account only after checking it independently, for example by calling a number already on record.</p></div>
<ul class="divide-y divide-slate-100">${d.changes.map(changeItem).join('')}</ul></section>` : ''}
<section class="bg-white border rounded-xl overflow-hidden">
<div class="px-4 sm:px-5 py-4 border-b border-slate-100 flex items-baseline justify-between gap-3"><h2 class="text-[16px]">Invoices <span class="text-slate-400 font-normal">${d.invoices.length}</span></h2>
<a href="/invoices" data-optional class="text-[13px] text-indigo-700 hover:underline">All invoices ›</a></div>
${list(d.invoices, 'No invoices need you right now.')}</section>
<section class="bg-white border rounded-xl overflow-hidden">
<div class="px-4 sm:px-5 py-4 border-b border-slate-100 flex items-baseline justify-between gap-3"><h2 class="text-[16px]">Vendor decisions <span class="text-slate-400 font-normal">${d.apps.length}</span></h2>
<a href="/applications" class="text-[13px] text-indigo-700 hover:underline">All applications ›</a></div>
${list(d.apps, 'No vendor decisions need you right now.')}</section></div>`;
qsa('form[data-decide]', view).forEach(f => f.addEventListener('submit', async e => {
e.preventDefault();
const err = qs('[data-error]', f), note = f.note.value.trim();
qsa('button', f).forEach(b => { b.disabled = true; });
try {
await api(`/change-requests/${f.dataset.decide}/decision`, { method: 'POST', body: { decision: e.submitter.value, note } });
await App.views['/review'].render(view);
} catch (x) {
err.textContent = x.message; err.hidden = false;
qsa('button', f).forEach(b => { b.disabled = false; });
}
}));
if (location.hash === '#changes') qs('#changes', view)?.scrollIntoView();
},
};
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
const VTONE = { active: 'text-emerald-700', onboarding: 'text-amber-700', rejected: 'text-rose-700', on_record: 'text-slate-600', inactive: 'text-slate-500' };
const PTONE = { eligible: ['Eligible', 'text-emerald-700'], blocked: ['Blocked', 'text-rose-700'], not_yet: ['Not yet', 'text-slate-500'] };
App.views['/vendors'] = {
title: 'Vendors',
async render(view) {
const params = new URLSearchParams(location.search);
const f = Object.fromEntries(['q', 'status', 'risk', 'pay', 'inv', 'sort'].map(k => [k, params.get(k) || '']));
const d = await api('/vendors?' + new URLSearchParams(f));
const filtered = Object.values(f).some(Boolean);
const sel = (name, label, opts) => `<label class="flex flex-col gap-1 text-slate-500">${label}<select name="${name}" class="rounded-lg border px-2 py-2 text-slate-800">${opts.map(([k, l]) => `<option value="${k}"${k === f[name] ? ' selected' : ''}>${l}</option>`).join('')}</select></label>`;
const money = n => n ? inr(n) : '—';
const rows = d.vendors.map(v => {
const risk = !d.full ? '' : `<td class="px-2 py-3" data-label="Risk">${v.risk.open ? `<span class="tag dot ${v.risk.fraud ? 'text-rose-700' : 'text-amber-700'}">${v.risk.open} open</span>` : v.risk.linked ? '<span class="tag text-amber-700">linked</span>' : '<span class="text-slate-400">none</span>'}</td>`;
return `<tr class="group hover:bg-slate-50/80 cursor-pointer" data-href="/vendors/${esc(v.id)}">
<td class="pl-5 pr-2 py-3 min-w-[15rem]"><div class="flex items-center gap-3">${monogram(v.name)}<div class="min-w-0">
<a href="/vendors/${esc(v.id)}" class="block font-medium text-slate-900 group-hover:text-indigo-700">${esc(v.name)}</a>
<div class="mt-0.5 text-[11.5px] text-slate-500"><span class="mono">${esc(v.id)}</span>${v.erp_id ? ` · <span class="mono">${esc(v.erp_id)}</span>` : ''}</div></div></div></td>
${d.full ? `<td class="px-2 py-3 mono text-[11.5px] text-slate-600" data-label="PAN · GSTIN">${esc(v.pan || '—')}${v.gstins.map(g => `<div>${esc(g)}</div>`).join('')}</td>` : ''}
<td class="px-2 py-3" data-label="Onboarding"><span class="tag dot ${VTONE[v.status] || 'text-slate-500'}">${esc(v.status_label)}</span>${v.latest_application ? `<div class="text-[11.5px] text-slate-500 mono mt-0.5">${esc(v.latest_application)}</div>` : ''}</td>
${risk}
<td class="px-2 py-3" data-label="Payment"><span class="${PTONE[v.payment][1]} font-medium">${PTONE[v.payment][0]}</span></td>
<td class="px-2 py-3 text-right tabular-nums" data-label="Active invoices">${v.active_invoices || '—'}</td>
<td class="px-2 py-3 text-right tabular-nums" data-label="Awaiting review">${money(v.awaiting_review)}</td>
<td class="px-2 py-3 text-right tabular-nums" data-label="Approved, unpaid">${money(v.approved_unpaid)}</td>
<td class="px-2 py-3 text-[12px] text-slate-500 whitespace-nowrap" data-label="Last activity">${esc(v.last_activity.label || '—')}</td>
<td class="pr-5 pl-2 py-3 text-[12.5px] font-medium text-slate-800" data-label="Next best action">${esc(v.next || '—')}</td></tr>`;
}).join('');
view.innerHTML = `<div class="space-y-5"><div><h1>Vendors</h1>
${d.full ? '' : '<p class="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[12.5px] text-amber-900">Only the vendors you asked for.</p>'}</div>
<form id="v-filter" class="flex flex-wrap items-end gap-2 text-[12.5px]">
<input name="q" value="${esc(f.q)}" type="search" placeholder="Name, VND- or V- number" aria-label="Search vendors" class="w-full sm:w-64 rounded-lg border px-3 py-2">
${sel('status', 'Onboarding', [['', 'Any'], ['onboarding', 'Onboarding'], ['active', 'Active'], ['rejected', 'Rejected'], ['on_record', 'On record']])}
${d.full ? sel('risk', 'Risk', [['', 'Any'], ['flagged', 'Open flags']]) : ''}
${sel('pay', 'Payment', [['', 'Any'], ['eligible', 'Eligible'], ['blocked', 'Blocked'], ['not_yet', 'Not yet']])}
${sel('inv', 'Invoices', [['', 'Any'], ['needs_review', 'Need review'], ['unpaid', 'Approved, unpaid']])}
${sel('sort', 'Sort', [['', 'Needs action first'], ['activity', 'Last activity'], ['awaiting', 'Awaiting review (₹)'], ['unpaid', 'Approved, unpaid (₹)']])}
<button class="rounded-lg bg-indigo-600 text-white font-semibold px-4 py-2 hover:bg-indigo-700">Apply</button>
${filtered ? '<a href="/vendors" class="px-2 py-2 text-indigo-700 hover:underline">Clear</a>' : ''}</form>
<section class="bg-white border rounded-xl overflow-hidden">${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-[13px]">
<thead class="text-left text-slate-500 bg-slate-50/70 border-b border-slate-100"><tr><th class="pl-5 pr-2 py-2.5">Vendor</th>${d.full ? '<th class="px-2">PAN · GSTIN</th>' : ''}<th class="px-2">Onboarding</th>${d.full ? '<th class="px-2">Risk</th>' : ''}<th class="px-2">Payment</th><th class="px-2 text-right">Active invoices</th><th class="px-2 text-right">Awaiting review</th><th class="px-2 text-right">Approved, unpaid</th><th class="px-2">Last activity</th><th class="pr-5 pl-2">Next best action</th></tr></thead>
<tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>`
: emptyState(filtered ? 'No vendor matches' : 'No vendors yet', filtered ? 'Try other filters.' : 'Vendors appear after their first check, and existing vendor-master records are included.')}</section></div>`;
qs('#v-filter', view).addEventListener('submit', e => {
e.preventDefault();
const p = new URLSearchParams();
for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
navigate('/vendors' + (p.toString() ? '?' + p : ''));
});
},
};
App.views['/invites'] = {
title: 'Invites',
async render(view, created) {
const made = new URLSearchParams(location.search).get('created');
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
App.views['/purchase-orders'] = {
title: 'Orders',
async render(view) {
const q = new URLSearchParams(location.search).get('q') || '';
const d = await api('/purchase-orders?' + new URLSearchParams({ q }));
const dot = (c, label) => `<span><span class="inline-block h-3 w-3 rounded-full ${c} align-middle mr-1.5"></span>${label}</span>`;
const rows = d.orders.map(o => `<tr class="group cursor-pointer row-${o.tone}" data-href="/purchase-orders/${o.id}">
<td class="pl-5 pr-2 py-3 whitespace-nowrap"><a href="/purchase-orders/${o.id}" class="mono text-[12.5px] font-medium ${o.tone === 'red' ? 'text-rose-800' : ''}">${esc(o.number)}</a>
<div class="text-[11.5px] text-slate-500">${esc(o.cost_centre)} · ${esc(o.status)}</div>
${o.issues.length ? `<div class="mt-1 text-[11.5px] font-semibold text-rose-700">${o.issues.map(esc).join(' · ')}</div>` : ''}</td>
<td class="px-2 py-3" data-label="Vendor">${esc(o.vendor.name)}<div class="text-[11.5px] text-slate-500 mono">${esc(o.vendor.gstin)}</div></td>
<td class="px-2 py-3 text-[13px]" data-label="Requested by">${esc(o.requested_by || '—')}</td>
<td class="px-2 py-3 text-right tabular-nums" data-label="Order value">${inr(o.total)}</td>
<td class="px-2 py-3 text-right tabular-nums ${o.delivered < o.total ? 'text-amber-700' : ''}" data-label="Delivered">${inr(o.delivered)}${o.delivery_recorded ? '' : '<div class="text-[11.5px] text-amber-700">not recorded</div>'}</td>
<td class="px-2 py-3 text-right tabular-nums" data-label="Invoiced">${o.invoiced !== null ? inr(o.invoiced) : '—'}</td>
<td class="pr-5 pl-2 py-3 text-right tabular-nums" data-label="Paid">${o.paid ? inr(o.paid) : '—'}</td></tr>`).join('');
view.innerHTML = `<div class="space-y-6">
<div class="flex flex-wrap items-end justify-between gap-4"><div><h1>Orders</h1>
<p class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-slate-600">${dot('bg-rose-500', 'Mismatch')}${dot('bg-amber-400', 'In progress')}${dot('bg-emerald-400', 'Settled')}</p></div>
<div class="flex gap-2 w-full sm:w-auto"><form id="po-search" class="flex-1"><input name="q" value="${esc(q)}" type="search" placeholder="PO number, vendor or cost centre" aria-label="Search purchase orders" class="w-full sm:w-64 rounded-lg border px-3 py-2 text-[13px]"></form>
<a href="/purchase-orders/new" class="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold px-4 py-2 hover:bg-indigo-700">+ New PO</a></div></div>
<section>${rows ? `<div class="overflow-x-auto"><table class="rtable tiles w-full text-sm"><thead class="text-left text-slate-500"><tr>
<th class="pl-5 pr-2 py-2.5">PO</th><th class="px-2">Vendor</th><th class="px-2">Requested by</th><th class="px-2 text-center">Order value</th><th class="px-2 text-center">Delivered</th><th class="px-2 text-center">Invoiced</th><th class="pr-5 pl-2 text-center">Paid</th></tr></thead>
<tbody>${rows}</tbody></table></div>`
: `<div class="bg-white border rounded-xl">${emptyState(q ? 'No purchase order matches' : 'No purchase orders', q ? 'Try another search.' : 'Create one with "New PO". Invoices from active vendors are matched against them.')}</div>`}</section></div>`;
qs('#po-search', view).addEventListener('submit', e => {
e.preventDefault();
const v = new FormData(e.target).get('q');
navigate('/purchase-orders' + (v ? '?' + new URLSearchParams({ q: v }) : ''));
});
},
};
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
App.views['/supplier-accounts'] = {
title: 'Accounts',
async render(view) {
const d = await api('/supplier-accounts');
const card = a => `<section class="bg-white rounded-xl border p-4 sm:p-5">
<div class="flex flex-wrap items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-3 min-w-0">${monogram(a.company, 'h-10 w-10 text-[13px]')}
<div class="min-w-0"><div class="font-semibold text-[15.5px]">${esc(a.company)}</div><div class="text-xs text-slate-500 mt-0.5 break-all">${esc(a.contact)} · <a class="hover:underline" href="mailto:${esc(a.email)}">${esc(a.email)}</a> · account since ${esc(a.since.label)}</div></div></div></div>
${a.vendor_id ? `<div class="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5"><span class="text-[11.5px] font-medium text-emerald-700">Vendor ID</span><span class="mono text-[14px] font-medium text-emerald-900">${esc(a.vendor_id)}</span></div>` : ''}</div>
<div class="mt-3 flex flex-wrap gap-2 text-sm">
${a.pending_invites.map(n => `<span class="tag text-violet-600">invited by ${esc(n)} · not submitted</span>`).join('')}
${a.registrations.map(r => `<${r.run_id ? `a href="/runs/${r.run_id}"` : 'span'} class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/60 px-2.5 py-1.5 hover:border-indigo-300 hover:bg-white"><span class="mono text-[12px]">${esc(r.ref)}</span>${statusBadge(r.status)}<span class="text-xs text-slate-500">${esc(r.came_in)}</span></${r.run_id ? 'a' : 'span'}>`).join('')}
${a.registrations.length || a.pending_invites.length ? '' : '<span class="text-xs text-slate-500">Account created; no registration yet.</span>'}</div>
${a.bills.length ? `<div class="mt-3 text-xs text-slate-600">Bills: ${a.bills.map(b => `<a href="/bills/${b.id}" class="underline mr-2">${esc(b.ref)} ${inr(b.amount)} · ${esc(b.status)}</a>`).join('')}</div>` : ''}</section>`;
view.innerHTML = `<div><div class="kicker">Supplier portal accounts</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Accounts</h1>
<div class="mt-6 space-y-3">${d.accounts.length ? d.accounts.map(card).join('') : `<section class="bg-white rounded-xl border">${emptyState('No vendor accounts yet', "Vendors create one from the home page (I'm a vendor or supplier).")}</section>`}</div></div>`;
},
};
const KIND_TAG = { reminder: '<span class="tag text-amber-700">reminder</span>', escalation: '<span class="tag text-rose-700">second reminder</span>' };
const EMAIL_TONE = { sent: 'text-emerald-700', failed: 'text-rose-700' };
App.views['/outbox'] = {
title: 'Outbox',
async render(view) {
const d = await api('/outbox');
const inbox = d.inbox.map(m => `<li class="px-4 sm:px-5 py-3 text-[13.5px]">
<div class="flex flex-wrap items-baseline gap-x-2"><b>${esc(m.name)}</b>${m.company ? `<span class="text-slate-500">· ${esc(m.company)}</span>` : ''}
<a class="text-indigo-700 hover:underline" href="mailto:${esc(m.email)}">${esc(m.email)}</a>${m.topic ? `<span class="tag text-slate-600">${esc(m.topic)}</span>` : ''}
<span class="ml-auto text-[12px] text-slate-500">${esc(m.received.label)}</span></div>
<p class="mt-1 text-slate-700 whitespace-pre-wrap">${esc(m.body)}</p></li>`).join('');
const cards = d.messages.map(m => `<div class="bg-white rounded-xl border p-4 sm:p-5">
<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
<span class="mono text-slate-500">${esc(m.ref)}</span><a href="/runs/${m.run_id}" class="text-indigo-700 underline">${esc(m.vendor)}</a>
<span class="text-slate-400">${esc(m.sent.label)}</span>${m.kind === 'note' ? `<span class="tag text-rose-700">to ${esc(m.to)}</span>` : (KIND_TAG[m.kind] || '')}
<span class="ml-auto tag ${m.state === 'sent' ? 'text-emerald-700' : 'text-amber-700'}">${esc(m.state)}</span>
${m.email ? `<span class="tag ${EMAIL_TONE[m.email.status] || 'text-slate-500'}">${esc(m.email.label)}${m.email.to ? ' to ' + esc(m.email.to) : ''}</span>` : ''}</div>
<div class="mono text-[11.5px] text-slate-500 mt-3 pt-3 border-t border-dashed border-slate-300">Subject: ${esc(m.subject)}</div>
<pre class="mt-1 whitespace-pre-wrap break-words font-display text-[16px] leading-relaxed text-slate-800">${esc(m.body)}</pre></div>`).join('');
view.innerHTML = `<div><div class="kicker">Correspondence</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">Vendor outbox</h1>
${inbox ? `<section class="mt-6 bg-white border rounded-xl overflow-hidden"><div class="px-4 sm:px-5 py-3.5 border-b border-slate-100"><h2 class="text-[16px]">From the Contact us form <span class="text-slate-400 font-normal">${d.inbox.length}</span></h2></div>
<ul class="divide-y divide-slate-100">${inbox}</ul></section>` : ''}
<div class="mt-6 grid xl:grid-cols-2 gap-3 items-start">${cards || '<p class="text-sm text-slate-500">No messages yet.</p>'}</div></div>`;
},
};
App.views['/system'] = {
title: 'System check',
async render(view, note = '') {
const d = await api('/system'), f = d.followups;
view.innerHTML = `<div><div class="kicker">Health</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">System check</h1>
${note ? `<div class="mt-4 rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-900">${note}</div>` : ''}
<div class="mt-6 bg-white rounded-xl border divide-y divide-slate-100 max-w-3xl">${d.checks.map(c => `<div class="p-4 flex gap-3 min-w-0">
<span class="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white ${c.ok ? 'bg-emerald-600' : 'bg-rose-600'}">${icon(c.ok ? 'check' : 'x', 'h-3.5 w-3.5')}</span>
<div><div class="text-sm font-medium">${esc(c.name)}</div><div class="text-xs text-slate-500 break-words">${esc(c.detail)}</div></div></div>`).join('')}</div>
${f.enabled ? `<section class="mt-8 max-w-3xl bg-white border p-4 text-sm"><div class="flex flex-wrap items-start gap-3"><div class="flex-1 min-w-0">
<div class="font-medium">Vendor follow-ups</div>
<div class="text-xs text-slate-500 mt-0.5">Runs by itself every ${f.every_hours} hours. Reminder after ${f.remind_after_days} days without an answer; after ${f.escalate_after_days} days a second reminder and a note to the employee who asked for the vendor.
${f.waiting} vendor${f.waiting === 1 ? '' : 's'} waiting now.${f.last ? ` Last follow-up sent ${esc(f.last.label)}.` : ''}</div></div>
<button type="button" id="fu-now" class="bg-indigo-600 text-white px-4 py-2 sm:py-1.5 font-semibold">Run follow-ups now</button></div>
<div id="fu-result" class="mt-3 border-l-4 border-l-slate-300 bg-slate-50 px-3 py-2 text-[12.5px]" hidden></div></section>` : ''}
<form id="reset-form" class="mt-8 max-w-3xl bg-white rounded-xl border p-4 flex flex-wrap items-center gap-3 text-sm">
<div class="flex-1 basis-full sm:basis-0 min-w-0"><div class="font-medium">Reset data</div><div class="text-xs text-slate-500">Deletes every run and reloads employees, invites, vendor master, blocklist and registry records.</div></div>
<input type="password" name="passcode" required placeholder="Passcode" aria-label="Passcode" autocomplete="off" class="flex-1 sm:flex-none min-w-0 rounded-md border px-3 py-2 sm:py-1.5">
<button class="rounded-md bg-rose-600 text-white px-4 py-2 sm:py-1.5">Reset</button>
<p class="basis-full text-[13px] text-rose-700" data-error hidden></p></form></div>`;
const btn = qs('#fu-now', view), out = qs('#fu-result', view);
if (btn) btn.onclick = async () => {
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
const crumb = (href, label, here) => `<div class="text-[13px] font-medium text-slate-500 flex items-center gap-1.5"><a href="${href}" class="hover:text-slate-900">${label}</a> ${icon('chev', 'h-3.5 w-3.5 text-slate-400')} <span class="text-slate-800">${here}</span></div>`;
const PO_STATE = { open: ['Open', 'text-amber-700 bg-amber-50'], closed: ['Closed', 'text-emerald-700 bg-emerald-50'], cancelled: ['Cancelled', 'text-rose-700 bg-rose-50'] };
const num = n => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
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
const LEVELS = [
['A0', 'Declared', 'The vendor typed it. Nothing backs it up.', 'A PAN in the form with no readable PAN card'],
['A1', 'Evidenced', "A document shows the same value, but we can't show the document is genuine.", 'A photo of a PAN card that has warnings, or a hand-written note'],
['A2', 'Genuine', 'A document shows it and the document looks genuine: no editing traces, a real photo or scan, nothing obscured.', 'A clear phone photo of a real PAN card'],
['A3', 'Cryptographically proven', 'The document carries a valid digital signature from the issuer, checked cryptographically.', 'A GST certificate downloaded from the portal, signed by GSTN, unchanged'],
['A4', 'Confirmed at source', 'The issuing authority confirmed it directly.', 'Bank branch via the live IFSC directory; in production also GSTN, NSDL PAN and a penny-drop'],
];
const SOURCES = [
['Reading documents (type, how it was made, fields)', 'Gemini reads every upload, blind to what the vendor typed', 'Google Gemini'],
['GST certificate digital signature', "Verified cryptographically, including GSTN's older SHA-1 format", 'The file itself'],
['Editing traces (Canva, Photoshop, PDF editors, re-saves)', 'From the file itself', 'The file itself'],
['GSTIN / PAN / IFSC structure, check digit, PAN inside GSTIN, state code', 'Calculated', 'Official formats'],
['Bank branch (IFSC)', "Live lookup, with a saved copy if it's down", 'RBI branch directory (Razorpay IFSC)'],
['PIN code, district and state', 'Live lookup', 'India Post PIN directory'],
['Address', 'Compared with the GST certificate; Google Address Validation when connected', 'GST certificate, Google'],
['Vendor master and blocklist (shared bank account, duplicates)', 'Compared on every check', 'Company vendor master'],
['GSTIN status and legal name', 'Registry lookup', 'GST registry'],
['PAN status and name', 'Registry lookup', 'PAN registry'],
['Bank account holder name (penny-drop)', 'A one-rupee penny-drop returns the holder name', 'Bank account verification'],
['Company (CIN) and MSME (Udyam) status', 'Registry lookup', 'MCA, Udyam'],
];
const DECISION = [
'<b>Rules decide; the AI only reads documents.</b> Every outcome traces to a named rule with its evidence.',
'Order: out of scope → <b>reject</b> → <b>internal review</b> → <b>vendor fixes</b> → <b>approved</b>. Approval requires every required rule to pass.',
'<b>Reject</b> only for an identity conflict (e.g. a GSTIN belonging to a different PAN) or the blocklist, and a person confirms before the vendor is told.',
'Authenticity heuristics never reject. A suspected fake goes to a person; the vendor gets a neutral "under review" message so a fraudster learns nothing.',
'"Couldn\'t read clearly" is never treated as "read and different": unclear documents mean "please upload a clearer copy". Misread characters are corrected only where provable (a PAN\'s letter positions, the GSTIN check digit); account numbers are never corrected.',
'<b>Bill-first registration:</b> a vendor who already did work can register at /bill with its invoice. The bill is checked (issued by this vendor, addressed to us, amount, arithmetic, CGST+SGST vs IGST, date, duplicates), the employee the vendor names must confirm the engagement, and that employee then counts as the requester. Bills of ₹10 lakh or more need the Finance controller. A bill is never paid automatically.',
"The employee who requested a vendor (the requester) can't approve it. High-risk vendors (≥ ₹50 lakh a year, or any fraud signal) need the Finance controller.",
'Approval is not payment: invoices are paid only after purchase-order and delivery matching.',
];
App.views['/assumptions'] = {
title: 'Help',
async render(view) {
const d = await api('/help');
view.innerHTML = `<div class="max-w-4xl"><div class="kicker">Honesty page</div>
<h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">What is verified, and what <em class="text-indigo-600">isn't</em></h1>
<section id="levels" class="mt-8"><h2 class="text-xl">How well a fact is proven</h2>
<p class="text-sm text-slate-600 mt-1">Every key fact (GSTIN, legal name, PAN, bank account) gets a level. A valid-looking number is only the start: someone can write a valid PAN on a blank sheet of paper.</p>
<div class="mt-3 bg-white rounded-xl border divide-y text-sm">${LEVELS.map(([lv, name, what, eg]) => `<div class="p-4 flex flex-col sm:flex-row gap-1.5 sm:gap-4"><div class="sm:w-52 shrink-0">${proofChip({ level: lv, name })}</div><div><div>${what}</div><div class="text-xs text-slate-500 mt-0.5">e.g. ${eg}</div></div></div>`).join('')}</div></section>
<section class="mt-8"><h2 class="text-xl">Where each answer comes from</h2><div class="mt-3 bg-white rounded-xl border overflow-hidden"><table class="rtable w-full text-sm">
<thead class="bg-slate-50 text-left text-xs text-slate-500"><tr><th class="px-4 py-2">Check</th><th class="px-2 py-2">How it's checked</th><th class="px-4 py-2">Source</th></tr></thead>
<tbody class="divide-y">${SOURCES.map(([c, how, src]) => `<tr><td class="px-4 py-2 font-medium sm:font-normal">${c}</td><td data-label="How it's checked" class="px-2 py-2 text-slate-700">${how}</td><td data-label="Source" class="px-4 py-2 text-slate-600">${src}</td></tr>`).join('')}</tbody></table></div></section>
<section class="mt-8"><h2 class="text-xl">How the decision is made</h2><ul class="mt-2 text-sm text-slate-700 list-disc pl-5 space-y-1">${DECISION.map(x => `<li>${x}</li>`).join('')}</ul></section>
<section class="mt-8"><h2 class="text-xl">Tested on imperfect real-world inputs</h2><div class="mt-3 grid md:grid-cols-2 gap-4 text-sm">
<div class="bg-white rounded-xl border p-4"><div class="font-medium">Blurry, compressed, tilted copies of genuine documents</div>
<p class="text-slate-600 mt-1">30 degraded copies of 6 genuine documents (blur, low-quality JPEG, 40% resolution, 3° tilt, phone-like): <b>60 of 60 fields read exactly, 0 wrong</b>, and no fraud flag on any real genuine document.</p></div>
<div class="bg-white rounded-xl border p-4"><div class="font-medium">Fakes it catches</div><ul class="text-slate-600 mt-1 list-disc pl-5 space-y-0.5">
<li>PAN hand-written on paper → vendor asked for the original</li><li>Photo of a screen, screenshot of a certificate → vendor asked for the file</li>
<li>Certificate edited in Canva → signature gone, editor recorded: fraud class</li><li>AI-generated PAN card and cheque → fraud class</li></ul></div></div></section>
<section id="access" class="mt-8"><h2 class="text-xl">Who sees what</h2>
<p class="text-sm text-slate-600 mt-1 max-w-3xl">Need to know. A requester may be the person a fraud check is about, so they don't see the checks, documents or ID numbers, only their own requests. Finance releases payments, so only Finance sees an active vendor's full bank account.</p>
<div class="mt-3 overflow-x-auto bg-white rounded-xl border"><table class="rtable w-full text-sm"><thead class="text-left text-slate-500 bg-slate-50 border-b border-slate-200"><tr><th class="pl-5 pr-2 py-2.5 font-medium">Information</th><th class="px-2 font-medium">Requester</th><th class="px-2 font-medium">Procurement reviewer</th><th class="pr-5 pl-2 font-medium">Finance controller</th></tr></thead>
<tbody class="divide-y divide-slate-100">${d.access.map(r => `<tr><td class="pl-5 pr-2 py-2.5 font-medium">${esc(r.information)}</td><td class="px-2 py-2.5" data-label="Requester">${esc(r.requester)}</td><td class="px-2 py-2.5" data-label="Procurement reviewer">${esc(r.reviewer)}</td><td class="pr-5 pl-2 py-2.5" data-label="Finance controller">${esc(r.finance)}</td></tr>`).join('')}</tbody></table></div></section>
<section class="mt-8 mb-4"><h2 class="text-xl">Assumptions and limits</h2><ul class="mt-2 text-sm text-slate-700 list-disc pl-5 space-y-1">
<li>Vendors are Indian and GST-registered; others go to a manual path.</li>
<li>Gemini's free tier allows 15 reads a minute; at most 2 applications run at once. If the AI is down, a saved reading of the same file is used and labelled.</li>
<li>Employees and vendors log in with email and password. In production employees would use the company's single sign-on.${d.demo ? ' The development person switcher is on in this environment.' : ''}</li></ul></section></div>`;
},
};
const BILL_TONE = { approved: 'text-emerald-700', rejected: 'text-rose-600', vendor_fix: 'text-amber-700', for_review: 'text-amber-700',
awaiting_confirmation: 'text-amber-700', ready_for_approval: 'text-emerald-700', checking: 'text-slate-500', failed: 'text-rose-600' };
App.views['/bills'] = {
title: 'Bills',
async render(view) {
const d = await api('/bills');
const conf = b => b.confirmation === 'confirmed' ? ' ✓' : b.confirmation === 'denied' ? ' <span class="text-rose-600">denies</span>' : '';
const rows = d.bills.map(b => `<tr class="hover:bg-slate-50 cursor-pointer" data-href="/bills/${b.id}">
<td class="pl-5 pr-2 py-3 whitespace-nowrap"><a href="/bills/${b.id}" class="mono text-[12.5px] hover:text-indigo-700">${esc(b.ref)}</a></td>
<td class="px-2 py-3 font-medium" data-label="Vendor"><span class="inline-flex items-center gap-2.5">${monogram(b.vendor.name, 'h-7 w-7 text-[10.5px]')}${esc(b.vendor.name)}</span> <span class="mono text-[11px] text-slate-500 font-normal">${esc(b.vendor.id)}</span>${b.fraud ? ' <span class="tag text-indigo-600 !text-[9px]">fraud class</span>' : ''}</td>
<td class="px-2 py-3 mono text-[12px]" data-label="Invoice">${esc(b.invoice_number || 'being read…')}</td>
<td class="px-2 py-3 text-right whitespace-nowrap" data-label="Amount">${inr(b.amount)}</td>
<td class="inline-sm px-2 py-3"><span class="tag ${BILL_TONE[b.status] || ''}">${esc(b.status_label)}</span></td>
<td class="inline-sm px-2 py-3">${tierChip(b.risk)}</td>
<td class="pr-5 pl-2 py-3 text-[13px] text-slate-600" data-label="Asked for by">${esc(b.asked_for_by || '')}${conf(b)}</td></tr>`).join('');
const regs = d.with_registration.map(r => `<li><a href="/runs/${r.run_id || ''}#bill" class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 sm:px-5 py-3 hover:bg-slate-50 text-sm">
${monogram(r.name, 'h-8 w-8 text-[11px]')}<span class="mono text-[12px] text-slate-500 w-20">${esc(r.ref)}</span>
<span class="flex-1 min-w-[12rem] font-medium">${esc(r.name)} <span class="mono text-[11.5px] text-slate-500 font-normal">${esc(r.invoice_number || '')}</span></span>
<span class="font-semibold tabular-nums">${inr(r.amount)}</span><span class="text-xs text-slate-500">${esc(r.asked_for_by || '')} · ${esc(r.confirmation)}</span></a></li>`).join('');
view.innerHTML = `<div><div class="kicker">Accounts payable</div><h1 class="text-[30px] sm:text-[38px] leading-tight mt-1">${d.full ? 'Bills' : 'Bills that name you'}</h1>
<section class="mt-6 bg-white rounded-xl border"><div class="px-4 sm:px-5 py-4 border-b border-slate-200"><h2 class="text-xl">From active vendors</h2></div>
${rows ? `<div class="overflow-x-auto"><table class="rtable w-full text-sm"><thead class="text-left text-slate-500 bg-slate-50 border-b border-slate-200"><tr><th class="pl-5 pr-2 py-2.5 font-medium">Ref</th><th class="px-2 font-medium">Vendor</th><th class="px-2 font-medium">Invoice</th><th class="px-2 font-medium text-right">Amount</th><th class="px-2 font-medium">Status</th><th class="px-2 font-medium">Risk</th><th class="pr-5 pl-2 font-medium">Asked for by</th></tr></thead>
<tbody class="divide-y divide-slate-100">${rows}</tbody></table></div>` : emptyState('No bills from active vendors yet', 'An active vendor sends them from the supplier portal; each is checked, then confirmed and approved here.')}</section>
<section class="mt-6 bg-white rounded-xl border"><div class="px-4 sm:px-5 py-4 border-b border-slate-200"><h2 class="text-xl">Sent with a registration</h2><p class="text-xs text-slate-500 mt-1">Vendors with no invite who registered with a bill for work already done. They're checked inside the registration run.</p></div>
${regs ? `<ul class="divide-y divide-slate-100">${regs}</ul>` : emptyState('None yet', 'Vendors who did work before registering send their bill with the registration.')}</section></div>`;
},
};
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
parts.push(`<div>${crumb('/vendors', 'Vendors', `<span class="mono">${esc(v.id)}</span>`)}
<div class="mt-2 flex flex-wrap items-start gap-4">${monogram(v.name, 'h-14 w-14 text-[18px]')}<div class="min-w-0 flex-1"><h1 class="break-words">${esc(v.name)}</h1>
<div class="mt-1.5 flex flex-wrap items-center gap-2 text-[12.5px] text-slate-500"><span class="tag dot ${VSTATE[v.status] || 'text-slate-500'}">${esc(v.status_label)}</span><span class="mono">${esc(v.id)}</span>
${v.erp_id ? `<span>· vendor master <span class="mono">${esc(v.erp_id)}</span></span>` : ''}${v.entity_type ? `<span>· ${esc(v.entity_type)}</span>` : ''}<span>· ${esc(v.country)}</span>
${v.open_flags ? `<span class="tag dot text-rose-600">${v.open_flags} open flag${v.open_flags === 1 ? '' : 's'}</span>` : ''}</div>
<p class="mt-2 text-[12.5px] text-slate-500 max-w-3xl">The vendor ID is ours and never changes. Applications are matched to it by PAN; shared bank accounts, addresses or files never merge two vendors, they appear below as relationships to check.</p></div></div></div>`);
if (v.cards) parts.push(`<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-[13px]">${v.cards.map(c => `<div class="bg-white border rounded-xl px-4 py-3 min-w-0"><div class="text-[12px] font-medium text-slate-500">${esc(c.label)}</div><div class="mt-0.5 font-semibold ${CARD_TONE[c.tone]}">${esc(c.value)}</div><div class="mt-0.5 text-[11.5px] text-slate-500 line-clamp-2">${esc(c.note)}</div></div>`).join('')}</div>`);
parts.push(section('next', 'What to do next', `<ol class="divide-y divide-slate-100">${v.next.map(a => `<li class="px-4 sm:px-6 py-3.5 flex gap-3"><span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${(PRIORITY[a.priority] || PRIORITY.normal)[0]}"></span>
<div class="flex-1 min-w-0"><div class="flex flex-wrap items-baseline gap-x-2 gap-y-1"><span class="text-[14.5px] font-semibold text-slate-900">${esc(a.title)}</span>${a.needs_integration ? '<span class="tag text-amber-700">needs a real provider</span>' : ''}</div>
${a.detail ? `<p class="mt-0.5 text-[13px] text-slate-600">${esc(a.detail)}</p>` : ''}
<p class="mt-1 text-[12px] text-slate-500"><b class="font-medium text-slate-600">Why:</b> ${esc(a.why)}${a.evidence.map(e => ' · ' + evLink(e)).join('')}${a.who.length ? ` · <b class="font-medium text-slate-600">Who:</b> ${a.who.map(esc).join(', ')}` : a.nobody ? ' · <b class="font-medium text-slate-600">Who:</b> nobody you can switch to right now' : ''}</p></div>
${a.href ? `<a href="${esc(a.href)}" class="self-center shrink-0 inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 hover:border-indigo-300 hover:text-indigo-700">Open ${icon('chev', 'h-3.5 w-3.5')}</a>` : ''}</li>`).join('')}</ol>`));
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
parts.push(section('risk', 'Risk flags', `<ul class="divide-y divide-slate-100">${v.risks.map(r => `<li class="px-4 sm:px-6 py-3.5 ${r.status === 'open' && r.fraud ? 'bg-rose-50/40' : ''}">
<div class="flex flex-wrap items-center gap-2"><span class="tag dot ${r.status === 'open' ? 'text-rose-600' : 'text-emerald-700'}">${esc(r.status)}</span>${r.fraud ? '<span class="tag text-rose-600">fraud class</span>' : ''}<span class="text-[14px] font-semibold text-slate-900">${esc(r.title)}</span></div>
<div class="mt-1 text-[12.5px] text-slate-500">${!r.mine && r.other ? `Raised on <a class="text-indigo-700 hover:underline" href="/vendors/${esc(r.other.id)}">${esc(r.other.name)}</a>, involving this vendor · ` : r.other ? `Involves <a class="text-indigo-700 hover:underline" href="/vendors/${esc(r.other.id)}">${esc(r.other.name)}</a> · ` : ''}rule ${esc(r.rule)} · check #${r.run_id} · opened ${esc(r.opened)}${r.evidence ? ' · ' + evLink(r.evidence) : ''}</div>
${r.action ? `<p class="mt-1.5 text-[13px] text-slate-700"><b class="font-semibold">Reviewer action:</b> ${esc(r.action)} <a class="ml-1 font-medium text-indigo-700 hover:underline" href="/runs/${r.run_id}#actions">Open the check</a></p>` : `<p class="mt-1.5 text-[13px] text-emerald-800">${icon('check', 'h-3.5 w-3.5 inline -mt-0.5')} ${esc(r.resolution || '')}</p>`}</li>`).join('') || '<li class="px-6 py-6 text-[13px] text-slate-500">No risk flags.</li>'}</ul>`));
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
view.addEventListener('click', e => {
const a = e.target.closest('a[href^="#ev-"]');
if (!a) return;
e.preventDefault();
const target = qs(a.getAttribute('href'), view);
if (target) { qs('#evidence', view).open = true; target.scrollIntoView({ block: 'center' }); target.classList.add('bg-indigo-50'); }
});
},
};
let leaveView = null;
function route(path) {
if (App.views[path]) return { screen: App.views[path], params: {} };
for (const [pattern, screen] of Object.entries(App.views)) {
if (!pattern.includes(':')) continue;
const names = [];
const re = new RegExp('^' + pattern.replace(/:([a-z_]+)/g, (_, n) => { names.push(n); return '([^/]+)'; }) + '$');
const m = path.match(re);
if (m) return { screen, params: Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(m[i + 1])])) };
}
return null;
}
async function show(path) {
const view = qs('#view'), found = route(path);
if (!found) { location.href = path + location.search + location.hash; return; }
if (leaveView) { leaveView(); leaveView = null; }
const { screen, params } = found;
document.title = `${typeof screen.title === 'function' ? screen.title(params) : screen.title} · Parakh Vendor Onboarding`;
qsa('a.side-link, #mainnav a').forEach(a => {
if (isOn(a.getAttribute('href'), path)) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
});
view.setAttribute('aria-busy', 'true');
try {
leaveView = (await screen.render(view, params)) || null;
dropDeadLinks(view);
const note = qs('#pending-note');
if (note && path.startsWith('/runs/')) note.hidden = true;
if (location.hash) qs(location.hash.replace(/[^#\w-]/g, ''), view)?.scrollIntoView();
} catch (e) {
if (e.status === 401) return;
view.innerHTML = `<div class="max-w-lg mx-auto mt-16 text-center"><h1 class="text-[28px]">${e.status === 403 ? "You can't open this" : e.status === 404 ? 'Not found' : "Couldn't load this"}</h1>
<p class="mt-3 text-slate-600">${esc(e.message)}</p>
<button type="button" data-retry class="mt-6 rounded-full bg-[#0071E3] text-white px-6 py-2.5 text-[14px] font-semibold">Try again</button></div>`;
qs('[data-retry]', view).onclick = () => show(path);
} finally {
view.removeAttribute('aria-busy');
}
}
function navigate(href, { replace = false } = {}) {
const url = new URL(href, location.href);
if (url.origin !== location.origin || !route(url.pathname)) { location.href = url.href; return; }
const target = url.pathname + url.search + url.hash;
if (target !== location.pathname + location.search + location.hash) history[replace ? 'replaceState' : 'pushState']({}, '', target);
show(url.pathname);
if (!url.hash) scrollTo(0, 0);
}
const reload = () => show(location.pathname);
async function boot() {
const root = qs('#app');
let session;
try { session = await api('/session'); } catch (e) { if (e.status !== 401) root.textContent = e.message; return; }
App.session = session;
root.innerHTML = renderShell(session, location.pathname);
await show(location.pathname);
if (!['/console', '/review'].includes(location.pathname)) refreshCounts();
}
document.addEventListener('click', e => {
const a = e.target.closest('a[href]');
if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute('download')) return;
const url = new URL(a.href, location.href);
if (url.origin !== location.origin || !route(url.pathname)) return;
if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
e.preventDefault();
navigate(url.href);
});
addEventListener('popstate', () => show(location.pathname));
document.addEventListener('DOMContentLoaded', () => {
mountSky(true);
wireShell();
boot();
});
})();
