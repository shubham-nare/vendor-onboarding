/* Start-up and moving between screens. Screens built in the app (App.views) open without reloading the page;
   any other link is an ordinary page load. The address bar, filters (?status=...) and the Back button work as usual.
   A screen's key is its path, or a pattern with :names for the parts that vary (e.g. '/runs/:id'). */

let leaveView = null;

// which screen draws this path, and the values of its :names
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
  document.title = `${typeof screen.title === 'function' ? screen.title(params) : screen.title} · Mamoni Vendor Onboarding`;
  qsa('a.side-link, #mainnav a').forEach(a => {
    if (isOn(a.getAttribute('href'), path)) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  view.setAttribute('aria-busy', 'true');
  try {
    leaveView = (await screen.render(view, params)) || null;
    dropDeadLinks(view);
    const note = qs('#pending-note');   // the reminder never covers a run page
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

// open a link: inside the app when it is an app screen, otherwise a normal page load
function navigate(href, { replace = false } = {}) {
  const url = new URL(href, location.href);
  if (url.origin !== location.origin || !route(url.pathname)) { location.href = url.href; return; }
  const target = url.pathname + url.search + url.hash;
  if (target !== location.pathname + location.search + location.hash) history[replace ? 'replaceState' : 'pushState']({}, '', target);
  show(url.pathname);
  if (!url.hash) scrollTo(0, 0);
}

// the same screen again, with fresh data (after an action on it)
const reload = () => show(location.pathname);

async function boot() {
  const root = qs('#app');
  let session;
  try { session = await api('/session'); } catch (e) { if (e.status !== 401) root.textContent = e.message; return; }
  App.session = session;
  root.innerHTML = renderShell(session, location.pathname);
  await show(location.pathname);
  if (!['/console', '/review'].includes(location.pathname)) refreshCounts();   // those two already list everything waiting
}

document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute('download')) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || !route(url.pathname)) return;
  if (url.pathname === location.pathname && url.search === location.search && url.hash) return;   // a jump within the page
  e.preventDefault();
  navigate(url.href);
});
addEventListener('popstate', () => show(location.pathname));

document.addEventListener('DOMContentLoaded', () => {
  mountSky(true);
  wireShell();
  boot();
});
