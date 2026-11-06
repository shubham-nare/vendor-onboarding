/* Core: talking to the JSON API, safe text, small helpers. Everything the app shows comes from /api/v1. */

const App = { session: null, views: {} };

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

// One way to call the API: JSON in, JSON out. A 401 sends the person to the right log-in page.
async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
  if (body instanceof FormData) opts.body = body;            // files: the browser sets the multipart boundary
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

// Every piece of text from the API goes through esc() before it is put on the page.
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];
const inr = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const store = {
  get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
