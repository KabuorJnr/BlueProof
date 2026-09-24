# BlueProof claims register

Every claim this project makes in public, and what stands behind it.

BlueProof sells belief. The ledger has no value except to someone who is willing
to trust it, and the moment a single unverifiable line is found in it the whole
record is worth nothing. So the standard here is stricter than for an ordinary
product: a claim that is merely plausible is not allowed to stand unmarked.

Status means: **Supported** — a source or a test, named here, that a sceptical
reader can check. **Estimate** — a calculation from a named external figure, with
its conditions stated wherever the number appears. **Unsupported** — believed,
not demonstrated, and therefore not stated as fact anywhere public. **Removed** —
was being claimed, is no longer.

---

## Verification

| Claim | Status | Evidence |
|---|---|---|
| Llama verifies mangrove species, seedling count, health, cutting and pest damage from a field photograph | **Unsupported** | No Llama model has ever been called by this project. Every verdict it has produced came from `_mock_verdict`, a SHA-256 keyed stub. `_verify_with_llama` is written and reviewed and has never executed. |
| The verification is accurate | **Unsupported** | Never measured. `tools/llama_eval.py` is the experiment that would measure it, against 100 photographs labelled by an expert in the field at the time of capture. It has not been run. |
| A general purpose vision model can discriminate Kenyan mangrove species from a handset photograph in a creek | **Unsupported, and the literature counsels caution** | The published work on vision models in field conditions reports sharp degradation on ordinary field imagery and fabricated species names at 5.9 to 9.6 percent on an open label set. That finding is the reason this system abstains rather than guesses; it is not evidence that the approach works. |
| The system declines rather than guesses | **Supported** | Three independent escalation reasons in `_record`: confidence below `min_verification_confidence`, health assessed as unclear, or the model's species disagreeing with the monitor's declaration. Verified end to end: disputed submissions reach `needs_human` and pay nothing. |
| The model never overwrites the monitor's declaration | **Supported** | On a species dispute the declaration is preserved, the event is escalated, and the monitor is told in Swahili that their answer stands because they were the one at the plot. |

What was done about it: `Verdict.source` is required and has no default, it is
persisted on `MonitoringEvent.verification_source`, it is carried into
`LedgerEntry.verification_source`, the field app shows it on the verdict screen,
and both apps display a standing demo notice while the backend reports a stub.
A ledger line that cannot say what verified it cannot be audited, and an
attestation that cannot be audited is not one.

## Satellite

| Claim | Status | Evidence |
|---|---|---|
| Sentinel-2 NDVI change corroborates the field record at hectare scale | **Unsupported as running** | The design is sound and the code path exists. The Eneo screen currently reads a generated series. The API reports `"satellite": "mock"` and the app names it in the demo notice. |
| Satellite cannot see seedlings | **Supported** | Sentinel-2 is 10 m resolution. A seedling is not resolvable at that scale. The app states this on the satellite screen rather than letting the imagery imply otherwise. |
| Cloud screening is applied | **Supported in code** | Observations carry `cloud_fraction` and the screened count is displayed. Not yet exercised against real scenes. |

## Carbon and credits

| Claim | Status | Evidence |
|---|---|---|
| Sequestration per hectare per year | **Unsupported** | `settings.co2_tonnes_per_ha_year` is an assumption. The API returns it as `indicative_co2_tonnes_per_year` alongside a `co2_basis` string that says in plain words it is an assumption awaiting validation. Validate with KMFRI or against a Plan Vivo methodology before it appears in any funding document. |
| The ledger meets a blue carbon standard's MRV requirement | **Unsupported** | No standard has reviewed it. Designed against the requirement, not accepted by anyone. |
| MRV cost is the binding constraint on Kenyan blue carbon, not community willingness | **Supported as a reading of the record** | Mikoko Pamoja issued roughly 22,169 credits over about fifteen years. The argument that verification cost rather than community appetite is what limits replication is an inference from that record, and it is presented in the paper as an argument, not a measurement. |

## Payments and the ledger

| Claim | Status | Evidence |
|---|---|---|
| A monitor is paid only on a verified submission | **Supported** | Payment is gated on `VerificationStatus.verified`; escalated submissions pay nothing. Verified end to end. |
| Payment is instant on M-Pesa | **Supported in code, untested in production** | STK push with mock, sandbox and live modes. Never run against production Daraja credentials. |
| The ledger is immutable | **Unsupported as worded** | Append only by construction. The database is not tamper evident. Say "append only". |

## Drone alternative

| Claim | Status | Evidence |
|---|---|---|
| Drone based monitoring is not a viable substitute at this stage | **Supported** | Kenya Civil Aviation Authority requirements: remote pilot licence, operator certificate, roughly thirty day processing. A real regulatory barrier for a two week build, independent of cost. |

---

## The one that matters most

Everything above is secondary to this: the paper describes an evaluation, the
deck rests on it, and it has never been run. Until it is, the central claim of
this project is untested.

`tools/llama_eval.py` reports species agreement, health agreement, fabrication
rate, cutting recall and precision, agreement split by accepted versus
abstained, and calibration across confidence buckets. It needs a rotated API key
and roughly 100 photographs labelled in the field.

A negative result is publishable and the architecture already accommodates one:
move species identification to a domain trained classifier and keep the language
model for legibility, condition, disturbance and the narrative. The only outcome
with no value is not running it and continuing to say the verification works.
