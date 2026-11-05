/* Mamoni Vendor Onboarding */
(()=>{'use strict';
const App = { session: null, views: {} };
class ApiError extends Error {
constructor(status, message) { super(message); this.status = status; }
}
async function api(path, { method = 'GET', body } = {}) {
const opts = { method, credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
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
const word = '<tspan class="bw-cap">M</tspan>amoni';
return `<a href="/" title="Home" aria-label="Mamoni Vendor Onboarding, home" class="brand-word shrink-0" data-full>
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
function navItems(session) {
const reviewer = ['maker', 'checker'].includes(session.actor.role);
return NAV.map(([group, items]) => [group, items.filter(([href]) => reviewer || !REVIEWER_ONLY.includes(href))]).filter(([, items]) => items.length);
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
if (reminded || !box || !d.count || path === '/console' || store.get('pending-hidden')) return;
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
<a href="/invoices" class="text-[13px] text-indigo-700 hover:underline">All invoices ›</a></div>
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
let leaveView = null;
async function show(path) {
const view = qs('#view'), screen = App.views[path];
if (!screen) { location.href = path + location.search + location.hash; return; }
if (leaveView) { leaveView(); leaveView = null; }
document.title = `${screen.title} · Mamoni Vendor Onboarding`;
qsa('a.side-link, #mainnav a').forEach(a => {
if (isOn(a.getAttribute('href'), path)) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
});
view.setAttribute('aria-busy', 'true');
try {
leaveView = (await screen.render(view)) || null;
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
function navigate(href) {
const url = new URL(href, location.href);
if (url.origin !== location.origin || !App.views[url.pathname]) { location.href = url.href; return; }
const target = url.pathname + url.search + url.hash;
if (target !== location.pathname + location.search + location.hash) history.pushState({}, '', target);
show(url.pathname);
scrollTo(0, 0);
}
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
if (url.origin !== location.origin || !App.views[url.pathname]) return;
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
