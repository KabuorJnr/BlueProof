#!/usr/bin/env python3
"""Evaluate the deployed verifier on real mangrove plot photographs.

This is the experiment the BlueProof paper specifies (section 6) and that
nothing in the project has yet run. Until it has been run, every accuracy
claim about the verification layer is unfounded.

It imports the production prompt, parser and gate threshold from the backend,
so the number it reports is a measurement of what is actually deployed, not of
a lookalike prompt.

It measures, per the paper:
  RQ1  corroboration: does the model accept correct declarations, and does it
       CATCH mistaken ones? Mistaken declarations are injected deliberately on
       a fraction of photographs (--mistake-rate), because the operationally
       important case is the one where the monitor is wrong.
  RQ2  disturbance recall and precision (cutting, pests).
  Abstention rate and quality: are errors concentrated in the abstained set?
  Fabrication: species offered outside the closed set of nine.
  Calibration: expected calibration error of the confidence that gates payment,
       for the deployed agreement-based confidence (--samples, default the
       deployed value) and for the model's self-reported figure beside it.
  Marker reading: accuracy reading plot codes, if labels carry marker_file
       and marker_code.
  Same place: accuracy judging whether two visits show the same place, if
       labels carry previous_file and same_location (1 or 0).

SECURITY: the API key is read from the environment. Never hardcode it, never
paste it into a chat window, never commit it. Rotate any key that has been
exposed.

    export OPENROUTER_API_KEY=sk-or-...
    python tools/llama_eval.py --photos ./photos --labels ./labels.csv --limit 10

labels.csv columns (one row per photograph):
    filename,species,health,cutting,pests[,declared][,marker_file,marker_code][,previous_file,same_location]

`species` must be the expert determination made in the field at time of capture,
not a guess from the photograph. `health` is one of healthy, stressed, dead.
`cutting` and `pests` are 0 or 1. `declared` is optional: what the monitor said.
Where absent, the script declares the true species, or a deliberately wrong one
on --mistake-rate of rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import mimetypes
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402
from app.services.gate import marker_mismatch  # noqa: E402
from app.services.llama_vision import (  # noqa: E402
    KENYAN_MANGROVE_SPECIES,
    PROMPT_VERSION,
    VerifierError,
    _extract_json,
    aggregate,
    build_messages,
    compare_messages,
    marker_messages,
    parse_comparison,
    parse_marker,
    parse_reply,
)
from app.services.photos import side_by_side  # noqa: E402

# Defaults come from backend/.env (LLAMA_API_URL, LLAMA_MODEL), so the eval
# measures the configured deployment unless told otherwise.
API_URL = settings.llama_api_url or "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = settings.llama_model


def norm(s) -> str:
    return str(s or "").strip().lower()


def wrong_species(true: str, filename: str) -> str:
    others = [s for s in KENYAN_MANGROVE_SPECIES if norm(s) != norm(true)]
    return others[int(hashlib.sha256(filename.encode()).hexdigest(), 16) % len(others)]


def declared_for(row: dict, mistake_rate: float) -> tuple[str, bool]:
    if row.get("declared"):
        return row["declared"], norm(row["declared"]) == norm(row["species"])
    roll = int(hashlib.sha256(("m" + row["filename"]).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if roll < mistake_rate:
        return wrong_species(row["species"], row["filename"]), False
    return row["species"], True


def chat(client: httpx.Client, url: str, key: str, model: str, messages: list,
         temperature: float, max_tokens: int = 400, retries: int = 3) -> str | None:
    payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "messages": messages}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(retries):
        try:
            r = client.post(url, json=payload, headers=headers)
            if r.status_code == 429:
                wait = 2 ** attempt * 5
                print(f"    rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            if attempt == retries - 1:
                print(f"    failed: {exc}", file=sys.stderr)
                return None
            time.sleep(3)
    return None


def ask(client, url, path: Path, declared: str, model: str, key: str, samples: int, temperature: float):
    """Run the deployed verifier: `samples` calls, aggregated the deployed way.

    Returns (raw replies, verdict). raw is None if every call failed, and
    [{"_unparseable": True}] if every reply was unusable.
    """
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    messages = build_messages(data, declared, mime)
    temp = 0.0 if samples == 1 else temperature
    raws, verdicts = [], []
    for _ in range(samples):
        content = chat(client, url, key, model, messages, temp)
        if content is None:
            continue
        try:
            raws.append(_extract_json(content))
            verdicts.append(parse_reply(content, declared, f"{model}@{PROMPT_VERSION}"))
        except VerifierError:
            # A model that cannot return the requested JSON is itself a finding.
            raws.append({"_unparseable": True})
    if not raws:
        return None, None
    # The deployed rule: a majority of samples must answer.
    if not verdicts or (samples > 1 and len(verdicts) * 2 <= samples):
        return [{"_unparseable": True}], None
    return raws, aggregate(verdicts, f"{model}@{PROMPT_VERSION}x{samples}")


def flag(value):
    """A 0/1 label, or None where the labels file leaves it blank (not assessed)."""
    value = str(value if value is not None else "").strip()
    return int(value) if value in {"0", "1"} else None


HEALTH_LABELS = {"healthy", "stressed", "dead"}


def pct(a, b):
    return f"{(100.0 * a / b):.1f}%" if b else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photos", required=True, type=Path)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api-url", default=API_URL, help="any OpenAI-compatible chat completions URL")
    ap.add_argument("--out", default="llama_eval_results.csv", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="stop after N photos (for a cheap pilot run)")
    ap.add_argument("--threshold", type=float, default=settings.min_verification_confidence,
                    help="confidence below which the system abstains (default: the deployed value)")
    ap.add_argument("--mistake-rate", type=float, default=0.3,
                    help="fraction of rows given a deliberately wrong declared species")
    ap.add_argument("--samples", type=int, default=settings.verifier_samples,
                    help="verifier calls per photograph, aggregated as deployed (default: the deployed value)")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLAMA_API_KEY") or settings.llama_api_key
    if not key:
        print("Set LLAMA_API_KEY in backend/.env (or OPENROUTER_API_KEY in your environment).", file=sys.stderr)
        return 2

    with args.labels.open(newline="", encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    if not truth:
        print("No rows in labels file.", file=sys.stderr)
        return 2
    if args.limit:
        truth = truth[: args.limit]

    species_set = {norm(s) for s in KENYAN_MANGROVE_SPECIES}
    rows = []
    with httpx.Client(timeout=120) as client:
        for i, t in enumerate(truth, 1):
            path = args.photos / t["filename"]
            if not path.exists():
                print(f"[{i}/{len(truth)}] {t['filename']}: MISSING", file=sys.stderr)
                continue
            declared, declared_ok = declared_for(t, args.mistake_rate)
            print(f"[{i}/{len(truth)}] {t['filename']}  declared={declared}", file=sys.stderr)
            raws, v = ask(client, args.api_url, path, declared, args.model, key,
                          args.samples, settings.verifier_sample_temperature)
            offered_all = [norm(r.get("species_if_different")) for r in (raws or [])]
            offered = next((o for o in offered_all if o), "")
            fabricated = any(o and o not in species_set | {"unclear", "none", "null"} for o in offered_all)

            marker_read, marker_ok = "", ""
            mfile = t.get("marker_file") and args.photos / t["marker_file"]
            if mfile and mfile.exists() and t.get("marker_code"):
                mime = mimetypes.guess_type(mfile.name)[0] or "image/jpeg"
                content = chat(client, args.api_url, key, args.model, marker_messages(mfile.read_bytes(), mime), 0.0, 80)
                try:
                    marker_read = parse_marker(content or "")["code"] or ""
                except VerifierError:
                    marker_read = ""
                marker_ok = int(bool(marker_read) and not marker_mismatch(marker_read, t["marker_code"]))

            same_pred, same_true = "", ""
            pfile = t.get("previous_file") and args.photos / t["previous_file"]
            if pfile and pfile.exists() and t.get("same_location", "") != "":
                stitched = side_by_side(pfile.read_bytes(), path.read_bytes(), "previous")
                content = chat(client, args.api_url, key, args.model, compare_messages(stitched), 0.0, 200)
                try:
                    same_pred = parse_comparison(content or "")["same_location"]
                except VerifierError:
                    same_pred = "unclear"
                same_true = "yes" if str(t["same_location"]).strip() in {"1", "yes", "true"} else "no"
            raw = (raws or [None])[0]
            rows.append({
                "filename": t["filename"],
                "true_species": t["species"],
                "declared": declared,
                "declared_correct": int(declared_ok),
                "consistent": v.species_consistent if v else "",
                "offered_species": offered,
                "fabricated": int(fabricated),
                "legible": int(v.legible) if v else "",
                "true_health": norm(t["health"]),
                "pred_health": v.health if v else "",
                "true_cutting": flag(t.get("cutting")),
                "pred_cutting": int(v.evidence_of_cutting) if v else "",
                "true_pests": flag(t.get("pests")),
                "pred_pests": int(v.pest_damage) if v else "",
                "confidence": v.confidence if v else "",
                "self_confidence": v.self_reported_confidence if v else "",
                "samples": v.samples if v else "",
                "marker_code": t.get("marker_code", ""),
                "marker_read": marker_read,
                "marker_correct": marker_ok,
                "same_location_true": same_true,
                "same_location_pred": same_pred,
                "unparseable": int(v is None and raw is not None),
                "failed": int(raw is None),
                "reasoning": v.reasoning if v else "",
            })

    if not rows:
        print("No photographs were found. Check --photos.", file=sys.stderr)
        return 2
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    usable = [r for r in rows if not r["failed"] and not r["unparseable"]]
    n = len(usable)
    print("\n" + "=" * 66)
    print(f"  Verifier evaluation  {args.model}  prompt {PROMPT_VERSION}")
    print("=" * 66)
    print(f"  photographs attempted          {len(rows)}")
    print(f"  usable responses               {n}  ({len(rows) - n} failed or unparseable)")
    if not n:
        print("\n  No usable responses. That is itself the result: report it.")
        return 0

    right = [r for r in usable if r["declared_correct"]]
    wrong = [r for r in usable if not r["declared_correct"]]
    print("\n  RQ1 corroboration")
    print(f"    correct declarations         {len(right)}")
    print(f"      accepted (yes)             {pct(sum(r['consistent'] == 'yes' for r in right), len(right))}")
    print(f"      falsely disputed (no)      {pct(sum(r['consistent'] == 'no' for r in right), len(right))}")
    print(f"      unclear                    {pct(sum(r['consistent'] == 'unclear' for r in right), len(right))}")
    print(f"    mistaken declarations        {len(wrong)}")
    print(f"      CAUGHT (no)                {pct(sum(r['consistent'] == 'no' for r in wrong), len(wrong))}")
    print(f"      MISSED (yes)               {pct(sum(r['consistent'] == 'yes' for r in wrong), len(wrong))}")
    print(f"      unclear                    {pct(sum(r['consistent'] == 'unclear' for r in wrong), len(wrong))}")
    print("    (the verification layer adds value only if CAUGHT is well above chance)")

    print(f"\n  fabricated species offered     {pct(sum(r['fabricated'] for r in usable), n)}")
    # Only rows whose labels say something are scored on that label. A corpus
    # labelled for species alone reports species alone.
    with_health = [r for r in usable if r["true_health"] in HEALTH_LABELS]
    if with_health:
        print(f"  health agreement               {pct(sum(r['pred_health'] == r['true_health'] for r in with_health), len(with_health))}")
    else:
        print("  health agreement               not labelled")
    print(f"  judged not legible             {pct(sum(not r['legible'] for r in usable), n)}")

    for name in ("cutting", "pests"):
        rs = [r for r in usable if r[f"true_{name}"] is not None]
        if not rs:
            print(f"  RQ2 {name:<8} not labelled   (flagged on {pct(sum(bool(r[f'pred_{name}']) for r in usable), n)} of photos)")
            continue
        tp = sum(1 for r in rs if r[f"pred_{name}"] and r[f"true_{name}"])
        fp = sum(1 for r in rs if r[f"pred_{name}"] and not r[f"true_{name}"])
        fn = sum(1 for r in rs if not r[f"pred_{name}"] and r[f"true_{name}"])
        print(f"  RQ2 {name:<8} recall {pct(tp, tp + fn):>7}   precision {pct(tp, tp + fp):>7}")

    # The deployed gate, minus the non-model checks (GPS, duplicates, cadence).
    def accepted(r):
        return (r["legible"] and r["pred_health"] != "unclear" and r["consistent"] == "yes"
                and float(r["confidence"]) >= args.threshold)

    def error(r):
        wrong_health = r["true_health"] in HEALTH_LABELS and r["pred_health"] != r["true_health"]
        return (not r["declared_correct"]) or wrong_health

    acc = [r for r in usable if accepted(r)]
    abst = [r for r in usable if not accepted(r)]
    print(f"\n  abstained (sent to a person)   {pct(len(abst), n)}   at threshold {args.threshold}")
    print(f"  error rate WHEN ACCEPTED       {pct(sum(map(error, acc)), len(acc))}   ({len(acc)} accepted)")
    print(f"  error rate WHEN ABSTAINED      {pct(sum(map(error, abst)), len(abst))}   ({len(abst)} abstained)")
    print("  (abstention works only if errors concentrate in the abstained set)")

    def calibration(field):
        buckets, correct = Counter(), Counter()
        for r in usable:
            if r[field] in ("", None):
                continue
            b = min(int(float(r[field]) * 10), 9)
            buckets[b] += 1
            correct[b] += not error(r)
        total = sum(buckets.values())
        ece = sum(buckets[b] / total * abs(correct[b] / buckets[b] - (b + 0.5) / 10) for b in buckets) if total else 0
        return ece, buckets, correct

    print(f"\n  calibration ({args.samples} sample(s) per photograph)")
    for field, label in (("confidence", "agreement (gates payment)"), ("self_confidence", "self-reported")):
        ece, buckets, correct = calibration(field)
        print(f"    {label:<28} ECE {ece:.3f}")
        for b in sorted(buckets):
            print(f"      {b / 10:.1f}-{(b + 1) / 10:.1f}   n={buckets[b]:<4} correct {pct(correct[b], buckets[b])}")
    print("    (lower ECE is better; agreement should beat self-report, or sampling is not worth its cost)")

    marked = [r for r in rows if r["marker_correct"] != ""]
    if marked:
        print(f"\n  marker codes read correctly      {pct(sum(r['marker_correct'] for r in marked), len(marked))}   ({len(marked)} markers)")
        misread = [r for r in marked if r["marker_read"] and not r["marker_correct"]]
        print(f"  read as a DIFFERENT code          {pct(len(misread), len(marked))}   (each one is a false fraud flag)")

    paired = [r for r in rows if r["same_location_true"]]
    if paired:
        same = [r for r in paired if r["same_location_true"] == "yes"]
        diff = [r for r in paired if r["same_location_true"] == "no"]
        print(f"\n  same place, recognised            {pct(sum(r['same_location_pred'] == 'yes' for r in same), len(same))}   ({len(same)} pairs)")
        print(f"  different place, CAUGHT           {pct(sum(r['same_location_pred'] == 'no' for r in diff), len(diff))}   ({len(diff)} pairs)")
        print(f"  same place, wrongly flagged       {pct(sum(r['same_location_pred'] == 'no' for r in same), len(same))}")

    print(f"\n  per photograph results written to {args.out}")
    print("\n  Report these numbers whatever they say. A negative result,")
    print("  honestly reported, is publishable and useful. An unmeasured")
    print("  claim is neither.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
