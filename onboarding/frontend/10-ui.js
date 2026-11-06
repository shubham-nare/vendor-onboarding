/* UI pieces shared by the screens: icons, badges, avatars, the brand word and the sky. */

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

// initials on a soft colour that is always the same for the same name
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

// the green-glass Parakh word; it always leads to the home page
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

// the sky behind every screen: clouds drift and lean toward the cursor, a soft glow follows it
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
