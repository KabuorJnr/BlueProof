# Specialist species classifier: BioCLIP + linear probe

24 September 2026. Follows `../2026-09-24-wikimedia-llama-3.2-11b/`, where
Llama 3.2 11B Vision could not tell the nine Kenyan species apart (0 of 20
wrong declarations caught when told the species; "unclear" on every photo when
not told). This is the paper's own fallback: a domain-trained classifier for
the species question, with Llama kept for legibility, condition, cutting,
pests, marker reading and reports.

## Result in one line

**On 533 held-out photos the classifier passes the pilot bar overall (accepts
87.1% of correct declarations, catches 98.7% of wrong ones), but not on the
45 East African photos (68.9% accepted) or for *Ceriops tagal* and *Xylocarpus
moluccensis* (37.5% each, 8 photos each).** Wrongly accepted declarations,
the ones that would be paid: 1.3% overall, 4.4% in East Africa.

## Method

| | |
|---|---|
| Features | BioCLIP (`hf-hub:imageomics/bioclip`), image embeddings, CPU |
| Classifier | Logistic regression, class-balanced; regularisation chosen on val |
| Data | iNaturalist research-grade, CC0/CC BY/CC BY-SA, ≤2 photos per observation. Manifests with licences and attribution in this folder; images not committed |
| Split | By observation, stratified per species. East African observations never in train |
| Decision | Given a declared species: yes if it is the top class ≥ t_yes; no if another class is top ≥ t_no; else unclear. Thresholds chosen on val |
| Test protocol | Every test photo scored twice: true species declared, and one deliberately wrong species |
| Pilot bar (agreed before measuring) | catch ≥ 80%, accept ≥ 85%, review ≤ 30% |
| Tool | `tools/build_dataset.py`, `tools/classifier.py` |

## Iterations

| | Iteration 1 | Iteration 2 |
|---|---|---|
| Photos (train / val / test) | 1,306 (855 / 192 / 259) | 2,750 (1,802 / 415 / 533) |
| East African photos | all 94 in test | 49 val, 45 test |
| Zero-shot top-1 on test (no training) | 64.5% | 67.5% |
| Probe top-1: val / **test** | 89.6% / **79.9%** | 86.7% / **87.1%** |
| Test: accept / catch / review | 79.9% / 98.5% / 0% | **87.1% / 98.7% / 0%** |
| Test East Africa: accept / catch | 63.8% / 93.6% | 68.9% / 95.6% |
| Pilot bar on test | does not pass | **passes overall** |

Changes from 1 to 2, fixed before looking at iteration-2 results: cap raised
from 200 to 600 photos per species; half the East African observations moved
to validation so thresholds were tuned on Kenyan-type imagery; thresholds
chosen for margin rather than a bare pass.

### Per species, iteration 2 test

| Species | n | Top-1 / accept | Catch |
|---|---|---|---|
| *Avicennia marina* | 111 | 92.8% | 100% |
| *Lumnitzera racemosa* | 111 | 91.9% | 100% |
| *Heritiera littoralis* | 23 | 91.3% | 100% |
| *Rhizophora mucronata* | 110 | 88.2% | 96.4% |
| *Bruguiera gymnorrhiza* | 94 | 83.0% | 98.9% |
| *Sonneratia alba* | 46 | 76.1% | 93.5% |
| *Xylocarpus granatum* | 22 | 100% | 100% |
| *Ceriops tagal* | 8 | **37.5%** | 87.5% |
| *Xylocarpus moluccensis* | 8 | **37.5%** | 100% |

*Ceriops* had about 22 training photos, the fewest of any Kenyan planting
species, and shares a family with *Rhizophora* and *Bruguiera*.

## The trust list

Accepting a correct declaration requires the top class to be right, so
thresholds cannot raise acceptance above top-1 accuracy; they can only move
wrong rejections into "unclear". To limit risk on weak species, a trust list
was chosen **on validation only**: auto-accept only species with ≥ 85%
validation acceptance and at least 5 validation photos. It selected
*Avicennia*, *Bruguiera*, *Heritiera*, *Lumnitzera*.

| Test | Correct declarations accepted | Correct declarations sent to a person | Wrong declarations accepted (would be paid) |
|---|---|---|---|
| No trust list | 87.1% | 12.9% | 1.3% |
| Trust list | 57.0% | 43.0% | 0.4% |
| East Africa, no trust list | 68.9% | 31.1% | 4.4% |
| East Africa, trust list | 31.1% | 68.9% | 2.2% |

Neither setting pays a disputed or unclear submission: those go to a person.
The trade is review workload against the small rate of wrong payments. The
backend defaults to the trust list (`SPECIES_TRUST_LIST=true`). Note that it
excludes *Rhizophora* and *Ceriops*, the main species planted at Tudor Creek,
so most Tudor Creek submissions would go to review under it.

## Honest limits

- **Test reuse.** The 45 East African test photos were scored in iteration 1
  and again in iteration 2 (and once more to report the trust list). 106
  non-African photos that were test in iteration 1 are training in iteration
  2 because the split was redrawn. Further iteration against these photos
  would overfit them; this is the stopping point for this dataset.
- **Small subsets.** East Africa n = 45: a 95% interval on 68.9% is roughly
  ±14 points. *Ceriops* and *X. moluccensis* n = 8 each.
- **Labels.** iNaturalist research grade is community-confirmed, not a field
  determination at a BlueProof plot.
- **Domain.** These are naturalist photos (leaves, flowers, whole trees), not
  monitor plot photos of seedlings. Performance on Tudor Creek plot photos is
  unmeasured.

## What would make it accurate enough for Kenya

Kenyan plot photographs, not more of the same. 100 or more Tudor Creek photos
per main species (*Rhizophora*, *Ceriops*, *Avicennia*, *Sonneratia*),
labelled in the field, would give both training data for the region and the
first genuinely unseen test. The pipeline takes them as they are:
`tools/classifier.py` accepts any manifest with the same columns.

## Using it

    pip install -r backend/requirements-ml.txt
    SPECIES_CLASSIFIER_PATH=app/models_data/species_probe.npz   # in backend/.env
    SPECIES_TRUST_LIST=true                                      # or false

About 50 s to load BioCLIP once, then 2–5 s per photo on a laptop CPU. It
needs about 1 GB of RAM, more than the free Render tier provides.
