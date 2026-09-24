# First model run: Llama 3.2 11B Vision on 60 Wikimedia photographs

24 September 2026. The first time any model has read a real mangrove photograph
in this project. Reported in full because the paper commits to reporting the
result whatever it says.

## Result in one line

**The model caught 0 of 20 deliberately wrong species declarations.** It agreed
with every species it was told, almost always unanimously across samples, so
under the deployed gate every one of those 20 would have been auto-verified and
paid. On this evidence the paper's first falsification criterion is met for this
model: corroboration of a mistaken declaration is not better than chance; it is
zero.

## Setup

| | |
|---|---|
| Model | `meta/llama-3.2-11b-vision-instruct` via NVIDIA's API catalog (the 90B model timed out on the free tier) |
| Prompt | `v3-bounded` (instructions in the user turn; see below) |
| Sampling | 3 samples per photo at temperature 0.7, aggregated by agreement, as deployed |
| Photos | 60 openly licensed Wikimedia Commons photos, 12 each of *Avicennia marina*, *Ceriops tagal*, *Rhizophora mucronata*, *Sonneratia alba*, *Xylocarpus granatum*. Credits in `photo-credits.csv` |
| Declarations | 30% deliberately wrong (deterministic per filename), 20 in the end |
| Tool | `tools/llama_eval.py`; re-derive every figure with `--from-csv results.csv` |

27 photos lost their calls to a local network outage in the first pass and were
re-run; declarations are fixed per filename, so the re-run tested the same
thing. Two photos were not retried because the model itself returned no usable
JSON on a majority of samples; they count as format failures.

## Numbers

| Measure | Result |
|---|---|
| Usable responses | 58 of 60 (2 format failures by the model) |
| Correct declarations accepted | 38 of 38 |
| **Wrong declarations caught** | **0 of 20** |
| Species names invented outside the nine | 0 (the model never disputed, so never offered one) |
| Judged not legible / condition unclear | 0 / 0; every photo rated "healthy" and "legible" |
| Sent to a person by the model-driven checks | 0% |
| Error rate among accepted | 34.5% (all 20 wrong declarations) |
| Calibration, agreement-based (ECE) | 0.284: 56 of 58 at agreement 0.9–1.0, of which 66% correct |
| Calibration, self-reported (ECE) | 0.391 |
| Mean agreement on the 20 misses | 0.98 (self-reported: 0.35) |

## What the failures look like

- A *Sonneratia alba* declared as *Ceriops tagal*: "The seedling's shape and
  leaves are consistent with Ceriops tagal."
- An egret in *Avicennia* canopy: "shows a large white bird standing in a tree
  with green leaves, which is consistent with the declared species."
- A pile of cut logs: the reasoning says "the image shows a pile of cut logs",
  and the structured answer says `cutting: false`. The gate acts on the
  structured answer.
- "Seedlings" appear in 43 of 60 reasonings, including photos of mature trees,
  flowers and fruit.

## What this does and does not show

**Does show.** With this prompt, this model is a rubber stamp: the declared
species is treated as a fact to confirm, not a claim to check. Sampling
agreement does not help, because the model is consistently wrong in the same
direction; it measures stability, not correctness. Self-reported confidence was
lower on the misses (0.35) than agreement (0.98), but it was low everywhere and
did not separate right from wrong either.

**Does not show.** Species labels are Wikimedia categories chosen by uploaders,
not field determinations. The photos are mostly curated shots of mature trees
from outside Kenya, not plot photographs of seedlings; the paper expects field
photos to be harder still. Health, cutting and pests were not labelled, so
those rates are unmeasured (the cut logs photo is a single observation, not a
rate). This is one small model; the 90B model and Llama 4 were not tested.

## Consequences for the design

1. **Do not let this model gate payment on species.** Until a model catches
   mistaken declarations well above chance, a species "yes" must not count
   towards auto-verification. The other gate checks (GPS, marker, duplicates,
   cadence, human review) still stand on their own.
2. **Test for sycophancy before anything else.** The next prompt should not
   reveal the declared species at all: ask the model to choose from the nine,
   then compare in code. That reintroduces the fabrication risk the paper
   designed against, so it needs the closed label set and abstention, and it
   needs measuring with this same harness.
3. **Structured answers must be checked against the reasoning**, or the
   reasoning must be dropped: the model wrote "cut logs" and answered
   `cutting: false`.
4. **Re-run with a larger model** (90B, or Llama 4 Scout/Maverick) when one is
   reachable, before concluding anything about Llama in general.
5. **The field photo set is still the real test.** 100 Tudor Creek plot photos,
   labelled in the field.

The 2 format failures (3%) are an operational finding; the submission path
already sends them to a person rather than guessing.
