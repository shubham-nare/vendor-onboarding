/* Start-up and moving between screens. Screens built in the app (App.views) open without reloading the page;
   any other link is an ordinary page load. The address bar and Back button work as usual. */

let leaveView = null;

async function show(path) {
  const view = qs('#view'), screen = App.views[path];
  if (!screen) { location.href = path; return; }
  if (leaveView) { leaveView(); leaveView = null; }
  document.title = `${screen.title} · Mamoni Vendor Onboarding`;
  qsa('[aria-current="page"]').forEach(a => a.removeAttribute('aria-current'));
  qsa('a.side-link, #mainnav a').forEach(a => { if (isOn(a.getAttribute('href'), path)) a.setAttribute('aria-current', 'page'); });
  view.setAttribute('aria-busy', 'true');
  try {
    leaveView = (await screen.render(view)) || null;
  } catch (e) {
    if (e.status === 401) return;
    view.innerHTML = `<div class="max-w-lg mx-auto mt-16 text-center"><h1 class="text-[28px]">Couldn't load this</h1>
      <p class="mt-3 text-slate-600">${esc(e.message)}</p>
      <button type="button" data-retry class="mt-6 rounded-full bg-[#0071E3] text-white px-6 py-2.5 text-[14px] font-semibold">Try again</button></div>`;
    qs('[data-retry]', view).onclick = () => show(path);
  } finally {
    view.removeAttribute('aria-busy');
  }
}

async function boot() {
  const root = qs('#app');
  let session;
  try { session = await api('/session'); } catch (e) { if (e.status !== 401) root.textContent = e.message; return; }
  App.session = session;
  root.innerHTML = renderShell(session, location.pathname);
  remind({ count: 0 }, location.pathname);
  await show(location.pathname);
}

document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute('download')) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || !App.views[url.pathname] || url.search) return;
  e.preventDefault();
  if (url.pathname !== location.pathname) history.pushState({}, '', url.pathname);
  show(url.pathname);
});
addEventListener('popstate', () => show(location.pathname));

document.addEventListener('DOMContentLoaded', () => {
  mountSky(true);
  wireShell();
  boot();
});
