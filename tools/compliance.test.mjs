/**
 * Compliance regression suite.
 *
 * Every check here corresponds to something that was fixed rather than
 * something that was always true. That is the point: a compliance pass which
 * lives only in a document decays the moment somebody adds a feature, so each
 * finding is pinned by an assertion that fails loudly when it comes back.
 *
 * BlueProof only. Run with the backend on :8011 (demo mode) and the app
 * preview on :4191:
 *   node compliance.test.mjs
 */
import { chromium } from 'playwright';
import { readFileSync } from 'fs';

const AXE = readFileSync('./node_modules/axe-core/axe.min.js', 'utf8');

const APPS = [
  {
    name: 'BlueProof',
    app: 'http://127.0.0.1:4191',
    api: 'http://127.0.0.1:8011',
    key: 'blueproof.apiBase',
    routes: ['#/plots', '#/site', '#/wallet', '#/queue', '#/settings', '#/privacy'],
    ref: 'BP-M-',
  },
];

let failures = 0;
function check(name, ok, detail = '') {
  if (ok) {
    console.log(`  PASS  ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL  ${name}${detail ? `  -- ${detail}` : ''}`);
  }
}

async function post(url, body, headers = {}) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
  return { status: r.status, body: await r.json().catch(() => null) };
}

const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium',
  args: ['--no-sandbox'],
});

for (const cfg of APPS) {
  console.log(`\n===== ${cfg.name} =====`);

  // ---- consent is a gate, not a checkbox -------------------------------
  const phone = `2547${Math.floor(10000000 + Math.random() * 89999999)}`;

  const noConsent = await post(`${cfg.api}/privacy/enrol`, {
    name: 'Compliance Test',
    phone,
    pin: '4321',
    consent_given: false,
  });
  check('enrolment without consent is refused', noConsent.status === 400);

  const minorNoGuardian = await post(`${cfg.api}/privacy/enrol`, {
    name: 'Compliance Test',
    phone,
    pin: '4321',
    consent_given: true,
    is_minor: true,
  });
  check(
    'a minor without a guardian is refused',
    minorNoGuardian.status === 400,
    `got ${minorNoGuardian.status}`,
  );

  const enrolled = await post(`${cfg.api}/privacy/enrol`, {
    name: 'Compliance Test',
    phone,
    pin: '4321',
    consent_given: true,
    is_minor: true,
    guardian_name: 'Test Guardian',
    guardian_phone: '254700000000',
  });
  check('a minor with a guardian is enrolled', enrolled.status === 200);
  check(
    'consent version is recorded, not just a boolean',
    Boolean(enrolled.body?.consent_version),
    JSON.stringify(enrolled.body),
  );
  check(
    'a pseudonym is issued at enrolment',
    String(enrolled.body?.public_ref || '').startsWith(cfg.ref),
    enrolled.body?.public_ref,
  );

  const userId = enrolled.body?.user_id;
  // BlueProof issues a session at enrolment and scopes export and deletion to
  // it; a record that anybody can export by guessing an id is not private.
  const auth = enrolled.body?.token ? { Authorization: `Bearer ${enrolled.body.token}` } : {};
  if (enrolled.body?.token) {
    const anon = await fetch(`${cfg.api}/privacy/export/${userId}`);
    check('export without a session is refused', anon.status === 401, `got ${anon.status}`);
  }

  // ---- export returns everything, including the unflattering parts -----
  const exported = await fetch(`${cfg.api}/privacy/export/${userId}`, { headers: auth }).then((r) => r.json());
  check('export includes the consent record', Boolean(exported.about_you?.consented_at));
  check(
    'export states what is NOT held',
    Array.isArray(exported.what_we_do_not_hold) && exported.what_we_do_not_hold.length > 0,
  );

  // ---- deletion actually deletes --------------------------------------
  const badPhrase = await post(`${cfg.api}/privacy/delete`, {
    user_id: userId,
    confirm_phrase: 'yes',
  }, auth);
  check('deletion without the confirm phrase is refused', badPhrase.status === 400);

  const deleted = await post(`${cfg.api}/privacy/delete`, {
    user_id: userId,
    confirm_phrase: 'FUTA',
  }, auth);
  check('deletion succeeds with the confirm phrase', deleted.status === 200);
  check(
    'deletion says what was kept and why',
    Array.isArray(deleted.body?.kept_and_why) && deleted.body.kept_and_why.length > 0,
  );

  const gone = await fetch(`${cfg.api}/privacy/export/${userId}`, { headers: auth });
  // 404 where there are no sessions; 401 where the session's account no longer exists.
  check('the person is gone afterwards, not flagged', [401, 404].includes(gone.status), `got ${gone.status}`);

  // ---- the model has not silently become the truth ---------------------
  const meta = await fetch(`${cfg.api}/`).then((r) => r.json());
  check(
    'the API never reports a verifier as "live" merely because a URL is set',
    meta.llama !== 'live',
    `llama=${meta.llama}`,
  );

  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const hosts = new Set();
  page.on('request', (r) => {
    try {
      hosts.add(new URL(r.url()).host);
    } catch {
      /* data: and blob: urls have no host */
    }
  });
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), [cfg.key, cfg.api]);
  // Every screen but sign in and settings needs a session; audit them signed in,
  // or every route would silently audit the sign in screen instead.
  const session = await post(`${cfg.api}/auth/login`, { phone: '254712000001', pin: '1111' });
  check('the demo monitor can sign in', session.status === 200, `got ${session.status}`);
  await page.addInitScript(
    (v) => localStorage.setItem('blueproof.session', v),
    JSON.stringify({ token: session.body?.token, user: session.body?.user }),
  );
  await page.goto(cfg.app, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);

  // ---- the demo notice is present while the backend is stubbed ---------
  const banner = await page.locator('.demobanner').count();
  check('a demo notice is shown while the verifier is a stub', banner === 1);
  const dismissible = await page.locator('.demobanner button').count();
  check('the demo notice cannot be dismissed', dismissible === 0);

  // ---- accessibility, every route --------------------------------------
  let violations = [];
  for (const route of cfg.routes) {
    await page.evaluate((r) => {
      location.hash = r;
    }, route);
    await page.waitForTimeout(350);
    await page.evaluate(AXE);
    const res = await page.evaluate(() =>
      window.axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      }),
    );
    for (const v of res.violations) violations.push(`${route}: ${v.id}`);
  }
  check('no WCAG 2.1 AA violations on any route', violations.length === 0, violations.join(', '));

  // ---- keyboard --------------------------------------------------------
  await page.goto(cfg.app, { waitUntil: 'networkidle' });
  await page.keyboard.press('Tab');
  const firstStop = await page.evaluate(() => document.activeElement.className);
  check('the first tab stop is the skip link', firstStop === 'skip', firstStop);

  await page.keyboard.press('Enter');
  const afterSkip = await page.evaluate(() => ({
    id: document.activeElement.id,
    hash: location.hash,
  }));
  check('the skip link moves focus to main', afterSkip.id === 'main');
  check(
    'the skip link does not break the hash route',
    afterSkip.hash !== '#main',
    afterSkip.hash,
  );

  await page.evaluate(() => {
    location.hash = '#/wallet';
  });
  await page.waitForTimeout(300);
  const routed = await page.evaluate(() => ({
    id: document.activeElement.id,
    title: document.title,
  }));
  check('a route change moves focus to the new view', routed.id === 'main');
  check('a route change updates the document title', routed.title.includes(cfg.name));

  // ---- storage ---------------------------------------------------------
  const cookies = await page.context().cookies();
  check('no cookies are set', cookies.length === 0, `${cookies.length} cookie(s)`);

  const offHost = [...hosts].filter(
    (h) => h !== new URL(cfg.app).host && h !== new URL(cfg.api).host,
  );
  check('no third party host is contacted', offHost.length === 0, offHost.join(', '));

  await page.close();
}

// ---- the ledger is auditable and pseudonymous ---------------------------
console.log('\n===== Ledger integrity =====');
{
  const api = 'http://127.0.0.1:8011';
  const login = await post(`${api}/auth/login`, { phone: '254712000001', pin: '1111' });
  const form = new FormData();
  form.append('plot_id', '1');
  form.append('client_ref', `compliance-${Date.now()}`);
  const submitted = await fetch(`${api}/monitoring/submit-photo`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${login.body?.token}` },
    body: form,
  }).then((r) => r.json());
  const event = submitted?.event;
  check('every verdict records which verifier answered', Boolean(event?.verification_source));
  check('a submission with no photograph is never paid', event?.status === 'needs_human' && !submitted?.payment);
  const unsigned = await fetch(`${api}/monitoring/submit-photo`, { method: 'POST', body: form });
  check('submission without a session is refused', unsigned.status === 401, `got ${unsigned.status}`);
  const chain = await fetch(`${api}/ledger/verify`).then((r) => r.json());
  check('the ledger hash chain verifies', chain.ok === true, JSON.stringify(chain));

  const report = await fetch(`${api}/mrv/report/1`).then((r) => r.json());
  const text = JSON.stringify(report);
  check(
    'no monitor name appears in the MRV report',
    !text.includes('Amina') && !text.includes('Juma') && !text.includes('Mwanaisha'),
  );
}

await browser.close();

console.log(
  `\n${failures === 0 ? 'All compliance checks passed.' : `${failures} check(s) FAILED.`}`,
);
process.exit(failures === 0 ? 0 : 1);
