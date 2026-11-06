/* Help: what is verified and what isn't. Fixed text lives here; the "who sees what" table comes from GET /api/v1/help
   so it is defined once, on the server, next to the rules that enforce it. */

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
