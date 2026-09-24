# Architecture

BlueProof is a small service with hard seams, so each external dependency can go
from mock to live independently without touching the flow.

## The chain of custody

```
Community monitor signs in and photographs a plot             (auth, photos)
  -> Photo hashed, stored, checked for duplicates and GPS distance
  -> Llama answers bounded questions against the declared species (llama_vision)
  -> Deterministic gate: verified | needs_human | rejected       (gate)
  -> needs_human: a CFA lead or verifier decides, with a reason  (review queue)
  -> Verified event triggers an M-Pesa B2C payout                (payouts, mpesa)
  -> Safaricom result callback settles it
  -> Hash-chained stewardship record written                     (ledger)
  -> Sentinel-2 NDVI corroborates at hectare scale              (sentinel)
  -> Llama drafts the monitoring narrative from those facts     (mrv_report)
  -> Buyer, funder or standard receives cheap, credible MRV
```

## Components

- **Backend, FastAPI.** System of record: users, sites, plots, monitoring events, satellite observations, payments, ledger.
- **Llama verification.** Open ended reasoning over a field photograph. Mock by default.
- **Sentinel-2 change detection.** Deterministic NDVI against a site baseline, with cloud screening. Mock series until Copernicus credentials are added.
- **M-Pesa.** Conditional payout, only ever called after verification passes.
- **MRV generator.** Facts assembled in code, narrative written by Llama.
- **Field assistant.** Swahili and Sheng guidance for monitors.
- **Dashboard.** Read view for the CFA, the county and a funder.

## Why the split matters

The single most common failure in AI for conservation is asking a language model
to do arithmetic or geometry it cannot do. Here the division is explicit:
deterministic code owns NDVI, thresholds, payment rules and the ledger. Llama
owns perception, language and drafting. Each can be audited on its own terms.

## Design choices

SQLite for zero setup in the MVP; point `DATABASE_URL` at Postgres, and add
PostGIS, when geometry queries matter. Geometry is stored as GeoJSON text to
avoid a spatial dependency this early. Every external service has a mock so the
whole flow demos offline, which matters when you are presenting on someone
else's wifi.
