# BlueProof

Mangrove restoration on the Kenyan coast is not blocked by a shortage of willing
communities. It is blocked by the cost of proving the work happened. BlueProof
makes that proof cheap.

A community monitor photographs a plot. A vision model answers a few bounded
questions about the photo: is it legible, what condition is visible, is there
cutting or pest damage, and is the monitor's declared species consistent with
it. A deterministic gate then checks that answer, the GPS distance to the plot,
duplicate photos, and whether the plot was already paid this cycle. If every
check passes, the monitor is paid over M-Pesa B2C and a hash-chained ledger line
is written. If any check fails, a person reviews the photo in the console, and
nothing is paid until they decide. Satellite NDVI corroborates at hectare
scale. The model drafts the monitoring narrative over facts assembled in code.

The design and its evaluation protocol are in `paper/BlueProof-paper.pdf`.

## What is built, and what is still unproven

| Part | State |
|---|---|
| Monitor sign in (phone + PIN, lockout), enrolment with recorded consent, CFA activation | Built, tested |
| Photo intake: SHA-256 + perceptual hash, duplicate detection, geofence, one paid event per plot per 7 days, idempotent offline retries | Built, tested |
| Verification gate, human review queue, audit trail of who approved what and why | Built, tested |
| Hash-chained ledger with `/ledger/verify` and CSV export | Built, tested |
| M-Pesa **B2C** payout with result/timeout callbacks, replay-safe, admin retry | Built. Tested against Daraja-shaped responses, **never against the sandbox** |
| Live Sentinel-2 via Copernicus Statistical API, SCL cloud masking, measured baseline, sustained-drop alerts | Built. Tested against API-shaped responses, **never against a real account** |
| Llama bounded verifier (prompt `v2-bounded`), confidence from agreement across 3 samples | Built, tested against a fake model. **No model has read a real mangrove photo.** |
| Plot marker reading (is this photo of *this* plot?) and comparison with the last verified visit (same place? what changed?) | Built, tested against a fake model |
| `tools/llama_eval.py`: the deployed prompts, sampling and parsers, measured on labelled photos | Built. Never run on real photos |

**The central claim is still untested.** Every verdict this repository has
produced came from a deterministic stub or from a fake model in the tests.
Whether a vision model can corroborate species and detect cutting on real
field photos is the question `tools/llama_eval.py` answers, and it needs
roughly 100 labelled photos from Tudor Creek. Every verdict carries its
`verification_source` into the ledger, and the apps show a non-dismissible
banner whenever anything is simulated.

**The sequestration figure is an assumption, not a measurement.** The API
labels it as one in every response.

## Run it

### Docker

```bash
docker compose up --build
```

- API at http://localhost:8000, interactive docs at http://localhost:8000/docs
- Field app (phone-sized PWA) at http://localhost:4173
- Staff console at http://localhost:8080

### Without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest                                                 # 45 tests
uvicorn app.main:app --reload
```

```bash
cd app && npm install && npm run build && npm run preview
```

Then serve `dashboard/` with any static server (`python -m http.server 8080 --directory dashboard`).

### Demo accounts (demo mode only)

| Who | Phone | PIN |
|---|---|---|
| Monitor Amina (BP-M-0001) | 0712000001 | 1111 |
| Monitor Juma (BP-M-0002) | 0712000002 | 2222 |
| CFA lead Mwanaisha (reviewer) | 254712000003 | 3333 |
| Admin | 254712000009 | 9999 |

With `ENVIRONMENT=production`, demo accounts are off and the first admin comes
from `ADMIN_PHONE` / `ADMIN_PIN`. The server refuses to start without a real
`SECRET_KEY`.

## Going live, one service at a time

Copy `.env.example` to `backend/.env`. Each block is independent.

1. **Verifier.** Set `LLAMA_API_URL`, `LLAMA_API_KEY`, `LLAMA_MODEL`. Run
   `tools/llama_eval.py` on labelled photos **before** you let it gate money.
2. **Satellite.** Set `COPERNICUS_CLIENT_ID/SECRET`. Draw the real site polygon
   (mangrove canopy only, not open water), then
   `POST /satellite/baseline/{site_id}` with a pre-restoration window to
   replace the assumed 0.62.
3. **Payments.** Set `MPESA_MODE=sandbox` and the `MPESA_*` block. Point
   `PUBLIC_BASE_URL` at a public HTTPS URL. Going to `production` needs a
   B2C-enabled shortcode on a **registered organisation**. That is a Safaricom
   onboarding process, not a code change.

## The flow

1. `POST /auth/login`: phone + PIN, returns a token.
2. `POST /monitoring/submit-photo`: photo, plot, GPS, `client_ref`. Runs the
   verifier and the gate (`services/gate.py`), then pays or escalates.
3. `GET /review/queue`, `POST /review/{id}`: a CFA lead or verifier approves or
   rejects, with a reason. Nobody reviews their own work.
4. `POST /mpesa/b2c/result`: Safaricom settles the payment. Only then is the
   ledger line written.
5. `GET /ledger`, `GET /ledger/verify`, `GET /ledger.csv`: the public,
   pseudonymous product.
6. `POST /satellite/refresh/{site_id}`, `GET /mrv/report/{site_id}`, `GET /impact/summary`.

## Where the model sits, precisely

- **Field verification** (`services/llama_vision.py`). Four bounded questions
  with a closed set of nine species. Anything off-menu is coerced to "unclear".
  It corroborates the monitor's declaration and never overwrites it. Asked
  three times; the **confidence that gates payment is the share of answers that
  agree**, not the number the model writes about itself (which is kept for the
  calibration study).
- **Plot marker reading.** The model reads the code off the marker shot; code,
  not the model, compares it with the plot. A marker for a different plot goes
  to a person. An unreadable one is recorded and does not block.
- **Comparison with the last verified visit.** The previous photo and today's
  are stitched side by side into one image, so single-image models work. "Not
  the same place" goes to a person; the change (improved, unchanged, declined)
  is recorded and never affects pay.
- **MRV narrative** (`services/mrv_report.py`). It writes prose over facts
  assembled in code. If anything is simulated, the report opens by saying so.
- **Field assistant** (`services/field_assistant.py`). Swahili guidance, with a
  rule-based fallback.

NDVI, thresholds, the payment gate, and the ledger are deterministic code.

## Two design decisions to defend

**Monitors are paid for a verified submission, not for a surviving seedling.**
If pay depended on survival, the incentive would be to hide deaths.

**Low confidence never auto-pays.** Every reason for not paying is written on
the submission, so a reviewer, and later an auditor, can see why.

## Honest limitations

See `docs/pilot-readiness.md` for what stands between this code and a real
pilot. Most of it is not code: KFS and CFA permission, a B2C shortcode, a
photo retention policy, labelled photos, and the MRV cost baseline.
