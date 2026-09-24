# The evaluation that has not been run

`llama_eval.py` runs a Llama vision model over real mangrove plot photographs
and compares its answers against expert field labels. It produces the metrics
the BlueProof paper specifies.

Nothing in this project has run it. Until it has, every accuracy claim about
the verification layer, including the ones in the deck and the paper, is
unfounded. This is the single highest value hour of work available to you.

## Before you run it

**Rotate any API key that has been exposed**, including any key pasted into a
chat window, an email, a screenshot or a commit. Then:

```bash
export OPENROUTER_API_KEY=sk-or-...        # never hardcode, never commit
```

Add `.env` and any key file to `.gitignore`. There is one in the repo root
already.

## Collect the photographs first

Follow `docs/field-photo-protocol.md`. The important part for the evaluation is
that conditions must be **ordinary**: the monitors' own handsets, the light and
tide they will actually work in. A corpus gathered on a perfect day with a good
phone produces a flattering number that will not survive deployment, which is
precisely the domain gap the literature describes.

Every photograph needs an expert label established **in the field at the time of
capture**, not inferred afterwards from the image. A label derived from the same
photograph being tested is not ground truth.

Start with 100 photographs. That is enough to find out whether the idea works.

## Run it

```bash
python tools/llama_eval.py \
  --photos ./photos \
  --labels ./labels.csv \
  --model meta-llama/llama-4-scout \
  --limit 10          # do a cheap pilot run first, then drop this
```

Use `--limit 10` on the first pass. It costs almost nothing and will surface a
bad prompt, a wrong model id or a malformed labels file before you spend on the
full set.

## Optional columns: marker and same place

Add `marker_file,marker_code` to measure how well the model reads plot markers,
and `previous_file,same_location` (1 or 0) to measure the same-place check.
Include some deliberately mismatched pairs, photographed at a different plot,
or the "caught" rate cannot be measured.

`--samples` defaults to the deployed value (3). Compare the two calibration
lines in the output: if agreement is not better calibrated than self-report,
set `VERIFIER_SAMPLES=1` and save the inference.

## Reading the output

**Species agreement** is the headline, but the more important pair is *agreement
when accepted* versus *agreement when abstained*. If those two numbers are
similar, the abstention mechanism is not doing anything and the confidence
threshold is decorative. Abstention is working only when errors concentrate in
the abstained set.

**Fabricated species labels** is a direct replication target. The published
figure for general purpose vision models is 5.9 to 9.6 percent on an open label
set. This script constrains the model to nine species, so a materially lower
rate would be a real and reportable finding.

**Cutting recall** matters more than precision. A false positive costs a human
review. A false negative loses a deforestation event.

**Calibration** tells you whether the confidence score means anything. If
accuracy is flat across confidence buckets, the threshold that gates payment is
gating on noise.

## What to do with the result

Report it either way.

If the model corroborates species usefully, you have the paper's central claim
supported and the deck becomes defensible.

If it does not, you have learned something genuinely worth publishing, and the
architecture already accommodates it: swap the species question to a
domain-trained classifier of the BioCLIP kind and keep Llama for legibility,
condition, disturbance and the report narrative. That was always the fallback in
the design, and it is a stronger system, not a retreat.

The one outcome with no value is not running it and continuing to say the
verification works.
