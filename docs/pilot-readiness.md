# Pilot readiness: is this practical?

Short answer: **the software is now practical. Whether the system works is
still unknown**, and the things that will decide it are mostly not code.

## What changed in this build, and why it mattered

The earlier demo ran end to end, but five problems would have stopped a real
pilot on the first day:

| Problem | Consequence | Now |
|---|---|---|
| M-Pesa used STK Push (`CustomerPayBillOnline`) | Every verified monitor would have been *asked to pay* KSh 150 | B2C `BusinessPayment` to the monitor; the ledger waits for Safaricom's result callback |
| No authentication; `monitor_id` taken from the request | Anyone could trigger unlimited payouts to any account, and export or delete anyone's data | Phone + PIN with lockout; payouts only to CFA-activated accounts; export and delete limited to the person themselves |
| No limits on repeat submissions | The same plot, or the same photo, paid every time it was submitted | One paid event per plot per 7 days; exact and near-duplicate photo detection; idempotent offline retries |
| No review queue; photos not stored | "Escalate to a human" went nowhere, and nobody could look at the evidence | Review queue in the console, with the photo, the reasons, and a required written decision |
| Text-only submissions could be paid; a model outage crashed the request | Payment without evidence; a lost submission | No photo means review; a verifier failure means review, never a crash |

Also fixed: the MRV report counted cutting and pest flags from every site, the
ledger was not tamper-evident, satellite alerts fired on a single scene, and
the eval tool tested a different prompt from production.

## Running cost of a Tudor Creek pilot (estimates to replace with measurements)

Assumptions: 42 ha, 30 plots, one paid submission per plot per week.

| Item | Estimate | Note |
|---|---|---|
| Monitor payments | ~1,560 events/yr × KSh 150 ≈ **KSh 234,000/yr** | This is meant to be the largest line. It is the money reaching people |
| B2C transaction charges | Per-transaction Safaricom tariff | Check the current B2C tariff for your shortcode |
| Model inference | Likely tens of US dollars/yr at this volume | Measure it in the eval run; the paper's cost study requires it |
| Sentinel-2 | Within the Copernicus free processing quota for a few sites | Statistical API returns numbers, no rasters |
| Hosting | Roughly US$10–30/month for a paid instance with disk and Postgres | The free tier loses photos on redeploy |
| **Human review** | At a 30% abstention rate, ~470 reviews/yr × ~2 min ≈ 16 h/yr | The paper's falsification criterion turns on this. The console now makes it measurable |

The software makes these costs small. What it cannot tell you is whether
anyone will pay for the resulting ledger, and at what price per hectare. That
is the commercial question in `risks-and-open-questions.md`, and it is still
open.

## What stands between this and a real pilot

In order of how much each blocks:

1. **Permission.** Kenya Forest Service and a Community Forest Association
   partner. Nothing else matters without this, and it is slow. Start now.
2. **The eval.** About 100 photos from Tudor Creek, each labelled in the field
   at the time of capture, run through `tools/llama_eval.py`. Until then, keep
   `LLAMA_API_URL` unset or treat every verdict as advisory. The architecture
   already survives a bad result: species can move to a specialist classifier
   and everything else stays.
3. **A B2C shortcode.** Real payouts need a registered organisation onboarded
   by Safaricom for B2C. The sandbox needs only a Daraja account. Until the
   shortcode arrives, pay manually from the console's payment list and keep
   `MPESA_MODE=mock`.
4. **The real site polygon and baseline.** Draw the boundary over mangrove
   canopy only, not open water. Then measure the baseline with
   `POST /satellite/baseline/{site_id}`. The assumed 0.62 will cause false alerts.
5. **Photo retention policy.** The mechanism exists (`PHOTO_RETENTION_DAYS`,
   `POST /admin/purge-photos`, and purge on deletion request). The number is a
   decision for you and the CFA, recorded in `data-inventory.md`.
6. **Production hosting.** Postgres, a persistent disk for photos, HTTPS, and a
   real `SECRET_KEY`. Add Alembic before the first schema change on pilot data;
   the server refuses to start on an out-of-date schema rather than failing
   mid-payment.

## Not verified in this build

- The Daraja B2C and Copernicus calls were tested only against responses shaped
  like the documented APIs. The first sandbox run may surface a field-name or
  auth detail. Both paths fail safely: a failed payout leaves the payment
  `failed` and retryable, and a failed satellite call keeps the previous series.
- Gate reasons are in English; the field app shows them as-is under a Swahili
  heading. They should be translated before monitors see them.
- One app instance only: the ledger lock is per process. Run one API worker
  until the ledger insert moves to a database-level lock.
