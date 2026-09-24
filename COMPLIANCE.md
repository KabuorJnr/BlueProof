# Compliance pass: BlueProof

September 2026. What was checked, what was found, what was changed, and how to
tell if it regresses.

Nothing below was asserted. Every finding came from running something, and every
fix is pinned by an assertion, either in `backend/tests/` (API behaviour) or in
`tools/compliance.test.mjs` (the running app, accessibility and network).

```
cd backend && pytest                 # API behaviour
node tools/compliance.test.mjs       # with the backend on :8011 and the app preview on :4191
```

---

## Accessibility

Audited with axe-core at 390×844 across every route in the field app, against
WCAG 2.1 A and AA.

**Two real violations found.**

Colour contrast, serious. The warning chip used `#B4531F` on its own tinted
background, giving 4.39:1 against a 4.5:1 requirement. Replaced with `#983F15`,
which measures 6.03:1 on the chip and 6.47:1 on the page background.

A missing label, critical. The visually hidden file input that the camera button
opens had no accessible name. It now carries a Swahili `aria-label` and
`tabIndex={-1}`: assistive technology can still reach it, and a keyboard user is
no longer dropped onto an invisible control that a visible button already
duplicates.

**Three defects axe cannot see, found by hand and fixed.**

No skip link. Added, route-safe: it prevents the default rather than letting the
browser set `location.hash` to `#main`, which in a hash-routed app would have
thrown the user back to the default view.

Focus never moved on a route change. `<main>` now receives focus on every route
change, skipping the first render so that arriving on the app does not steal
focus.

The document title never changed. Each route now sets its own.

Also: the decorative step indicator is `aria-hidden`, and the step is announced
through a live region because it advances by itself after a photo.

The sign in and enrolment screens added since use labelled inputs, real
checkboxes and `role="alert"` errors; they need re-running through axe.

## Unsupported claims

**No Llama model has ever run.** Rather than reword around that, the system says
so itself: the API reports `"mock"`, every verdict carries `verification_source`
into the event and the ledger, the verdict screen names the verifier, the apps
show a standing, non-dismissible demo notice while anything is stubbed, and the
MRV report opens with a bold demonstration-data warning whenever any record in
it came from the simulator.

**The sequestration figure is an assumption**, labelled as one in every response
that carries it.

**Satellite and payment integrations are built but unvalidated** against real
accounts, and `docs/pilot-readiness.md` says so.

Full detail in `docs/claims-register.md`.

## Data minimisation

**The ledger carried `monitor_name`.** That table is the product: it is exported,
shown to funders and sold to credit buyers, and each line already had a plot
code, a date and coordinates good to a few metres. A real name beside those
turned an environmental record into a published account of where an
identifiable young person stood on a given morning. For a monitor who reports
illegal cutting in their own community, that is a safety question.

It is now `monitor_ref`, a pseudonym. Reviewers appear the same way
(`reviewed_by_ref`). Phone numbers are shown only to staff; a monitor's own
payment list omits them.

**No date of birth is stored anywhere.** The only question the system needs
answered is whether a guardian must consent, which is a boolean.

## Consent, age, access and deletion

Built as code, not as a paragraph.

Enrolment refuses without consent and stores nothing. The consent *version* is
stored. A minor cannot be enrolled without a guardian's name and number.

Every personal endpoint needs a session. `GET /privacy/export/{id}` and
`POST /privacy/delete` work only for the person themselves (export also for
staff, delete also for an admin). Before this pass, anybody could export or
erase anybody by guessing an id.

Deletion erases the person and their photographs outright, keeps the
environmental record under a pseudonym that now points at nobody, keeps each
photograph's SHA-256 so the ledger still proves which image was assessed, and
says plainly that payment records survive for seven years under financial rules.

## Third party SDKs, fonts and licences

Four packages reach the phone: react, react-dom (MIT), lucide-react (ISC), plus
React's transitive dependencies. Backend packages are all permissive; Pillow
(MIT-CMU) was added for photo validation and hashing.

**No analytics, no crash reporting, no tag manager, no advertising SDK, no font
CDN.** The app talks only to its own backend. See `docs/third-party-audit.md`
and `docs/third-party-licences.md` (regenerate with `tools/licences.sh`).

## Cookies

There are none. The session is a bearer token in localStorage, sent only by the
app's own code. `legal/cookies-and-storage.md` lists every piece of browser
storage and why it is necessary.

## Dark patterns, hidden fees, fake reviews

The monitor receives the full flat payout; no fee or deduction exists in the
code. No countdown timers, false scarcity, pre-ticked consent or hidden
opt-outs. No reviews or testimonials exist. One genuine hardship is documented
rather than designed away: an escalated or rejected submission pays nothing
after the walk was made. Detail in `docs/fairness-audit.md`.

## Policies

`legal/privacy-policy.md`, `legal/terms-of-service.md` and
`legal/cookies-and-storage.md`, served with the app. A refund policy is not
applicable (money only moves outward); a payment dispute process replaces it,
backed by the review queue's named, reasoned decisions. No email is sent.

---

## What is still outstanding, and only you can do it

**Fill every `[FILL]` in the three policy files.** Registered name, registration
number, physical address, phone, email, and a named data protection contact.

**Register with the Office of the Data Protection Commissioner** before a real
monitor is enrolled.

**Decide how long photographs are kept**, then set `PHOTO_RETENTION_DAYS`. The
mechanism exists; the number is a decision.

**Revoke the exposed OpenRouter key.** It was in `.env.example`; it has been
removed from the file, but removal does not un-expose it.

**Run the Llama evaluation.** Everything else here is housekeeping next to this
one. `tools/llama_eval.py` needs a fresh key and about 100 photographs labelled
in the field, and a negative result is worth reporting.
