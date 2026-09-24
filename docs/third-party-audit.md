# Third party audit: BlueProof

What the software depends on, what licence each dependency carries, and what it
sends over the network. The outbound services specific to BlueProof are noted
at the end.

Everything below was checked against the installed packages and the built
bundle, not against the intentions in `package.json`.

---

## What reaches the monitor's phone

Four packages end up in the browser.

| Package | Version | Licence | Why it is there |
|---|---|---|---|
| react | 18.3.1 | MIT | UI |
| react-dom | 18.3.1 | MIT | UI |
| lucide-react | 0.454.0 | ISC | Icons |
| scheduler, loose-envify, js-tokens | transitive | MIT | Pulled in by React |

Build tooling (vite 5.4.21, `@vitejs/plugin-react` 4.7.0, both MIT) never
reaches the phone.

All permissive. MIT and ISC both permit commercial use, modification and
distribution, and both require the copyright notice and licence text to be
retained. The practical obligation is attribution, and it is met by
`docs/third-party-licences.md`, generated from the installed packages.

## What the app sends, and where

Every absolute URL in the built bundle, extracted from `dist/`:

```
http://localhost:8000                        the default backend, overridable in Settings
https://reactjs.org/docs/error-decoder.html  a string in React's error message, never fetched
http://www.w3.org/...                        XML namespace identifiers, never fetched
```

That is the complete list. Confirmed at runtime: a headless Chromium session
that loaded the app and visited every route recorded these hosts and no
others.

```
BlueProof: 127.0.0.1:4191 (the app itself), 127.0.0.1:8011 (its backend)
```

**No analytics. No crash reporting. No tag manager. No advertising or attribution
SDK. No font or icon CDN. No social pixel. No session recorder.** Nothing in
these apps talks to anybody except the backend the user configured.

This is worth stating plainly because it is unusual and it is the strongest
privacy fact about the project: there is no third party to audit for data
sharing, because there is no third party. It also means that the first time
someone proposes adding an analytics SDK, that decision will be a visible one
rather than a default inherited from a template.

## Fonts

No web fonts are loaded. The stack is:

```css
system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif
```

Every entry resolves to a font already installed on the device. Nothing is
downloaded, no font host sees a request carrying the user's IP address, and no
font is redistributed, so no font licence is engaged at all.

This was a performance decision first, on the reasoning that a monitor on a
2G connection should not wait on a typeface. It happens also to remove the
commonest way a small app leaks its users' IP addresses to a third party.

## Icons

Two sources, both clean.

**Interface icons** come from lucide-react, ISC licensed. Lucide is a community
fork of Feather, also ISC. Attribution is in the licence file; no per icon
attribution is required.

**App icons** (`icon-192.png`, `icon-512.png` in each app's `public/icons/`)
were generated for this project. They are not derived from any third party
artwork, stock library or brand mark.

## Backend packages

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| starlette | 1.0.0 | BSD-3-Clause |
| uvicorn | 0.46.0 | BSD-3-Clause |
| sqlmodel | 0.0.42 | MIT |
| sqlalchemy | 2.0.54 | MIT |
| pydantic | 2.13.3 | MIT |
| pydantic-settings | 2.14.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| python-multipart | 0.0.26 | Apache-2.0 |
| anyio | 4.13.0 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.13 | BSD-3-Clause |
| certifi | 2026.4.22 | MPL-2.0 |

All permissive. One point deserves a sentence because it is the only licence
here with a copyleft component: **certifi is MPL-2.0**, which is file level
copyleft. Using it as a dependency imposes nothing; modifying certifi's own
source would require publishing those modifications. Nothing here modifies it.

## Outbound calls the backend makes

| Destination | When | What is sent | Configured by |
|---|---|---|---|
| Llama vision endpoint | On a valuation with an image, only if `LLAMA_API_URL` is set | The photograph, base64, plus the grading prompt | `LLAMA_API_URL`, `LLAMA_API_KEY` |
| Safaricom Daraja | On payout, only in sandbox or live mode | Phone number, amount, reference | `MPESA_*` |

Both are off by default. In the default configuration the backend makes no
outbound calls at all.

The photograph is the significant one: enabling live grading means a monitor's
photograph, which may include their hands, their home or their neighbours,
leaves the country to whichever inference provider is configured. That is a
transfer decision under the Data Protection Act, not just a configuration
change, and it is recorded as such in the privacy notice rather than buried in
an environment variable.

## Credentials

No key, token or secret appears in any source file, and `.gitignore` excludes
`.env`, `*.key` and `OPENROUTER*`. Every credential is read from the environment
at runtime.

Two credentials have been exposed in chat during this project's development: a
Kaggle password and an OpenRouter API key. Neither was used. **Both must be
rotated.** An exposed key is exposed permanently; rotation is the only remedy,
and it is not optional because the key was never knowingly used by anyone.

## Satellite and payment services

**Copernicus / Sentinel Hub**,
for satellite imagery, configured by `COPERNICUS_CLIENT_ID` and
`COPERNICUS_CLIENT_SECRET` and currently unset. Requests to it carry a site
polygon and a date range, and no personal data.

The polygon is worth one thought even so. A monitoring site boundary is not
personal data, but published together with a named monitor it becomes a fairly
precise statement about where an identifiable person works. That is why the
ledger's identity handling is dealt with separately in the data inventory.

**Safaricom Daraja (M-Pesa B2C)**, configured by the `MPESA_*` settings and off
while `MPESA_MODE=mock`. Each payout sends the monitor's phone number, the amount
and a submission reference, which is the minimum a payment needs. Safaricom posts
the result back to `/mpesa/b2c/result`, authenticated by a secret token in the
callback URL.

## What is not audited here

Whatever inference provider ends up serving Llama is a data processor handling
photographs, and it is not covered by this document. Before live grading is
switched on, that provider needs its own assessment: where it processes, how
long it retains, whether it trains on submissions, and whether a data processing
agreement exists. A provider that retains photographs for model training is not
usable here without the monitors' informed and specific consent.
