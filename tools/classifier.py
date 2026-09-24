#!/usr/bin/env python3
"""Specialist species classifier: BioCLIP features + a trained linear probe.

The paper's fallback for species (section 4.4): a domain-trained classifier in
place of a general vision-language model, which on 2026-09-24 could not tell
these species apart at all (docs/evaluations/).

Steps, each reported separately so none can flatter another:
  1. Embed every photo with BioCLIP (cached to embeddings.npz).
  2. Zero-shot: nearest species name, no training.
  3. Linear probe: logistic regression on train; regularisation chosen on val.
  4. BlueProof decision: given a DECLARED species, answer yes / no / unclear.
     Thresholds are chosen on val to meet the pilot bar, then measured ONCE on
     test. Every test photo is scored twice: with its true species declared,
     and with one deliberately wrong species.

Pilot bar (agreed 2026-09-24), on held-out test photos:
  catch >= 80% of wrong declarations, accept >= 85% of correct ones,
  send <= 30% of all declarations to a person.

    python tools/classifier.py --data <dataset dir from build_dataset.py> --out <dir>

Needs backend/requirements-ml.txt.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.llama_vision import KENYAN_MANGROVE_SPECIES  # noqa: E402

MODEL_ID = "hf-hub:imageomics/bioclip"

# BioCLIP was trained on taxonomic strings; they zero-shot better than bare names.
TAXONOMY = {
    "Rhizophora mucronata": "Plantae Tracheophyta Magnoliopsida Malpighiales Rhizophoraceae Rhizophora mucronata",
    "Ceriops tagal": "Plantae Tracheophyta Magnoliopsida Malpighiales Rhizophoraceae Ceriops tagal",
    "Bruguiera gymnorrhiza": "Plantae Tracheophyta Magnoliopsida Malpighiales Rhizophoraceae Bruguiera gymnorhiza",
    "Avicennia marina": "Plantae Tracheophyta Magnoliopsida Lamiales Acanthaceae Avicennia marina",
    "Sonneratia alba": "Plantae Tracheophyta Magnoliopsida Myrtales Lythraceae Sonneratia alba",
    "Lumnitzera racemosa": "Plantae Tracheophyta Magnoliopsida Myrtales Combretaceae Lumnitzera racemosa",
    "Xylocarpus granatum": "Plantae Tracheophyta Magnoliopsida Sapindales Meliaceae Xylocarpus granatum",
    "Xylocarpus moluccensis": "Plantae Tracheophyta Magnoliopsida Sapindales Meliaceae Xylocarpus moluccensis",
    "Heritiera littoralis": "Plantae Tracheophyta Magnoliopsida Malvales Malvaceae Heritiera littoralis",
}
BAR = {"catch": 0.80, "accept": 0.85, "review": 0.30}


def load_manifest(data: Path) -> list[dict]:
    rows = list(csv.DictReader((data / "manifest.csv").open(encoding="utf-8")))
    img = data / "images"
    return [r for r in rows if (img / r["filename"]).exists()]


def embed(data: Path, rows: list[dict], cache: Path):
    import open_clip
    import torch
    from PIL import Image

    have = {}
    if cache.exists():
        # Plain string and float arrays only; pickled objects are never loaded.
        z = np.load(cache, allow_pickle=False)
        have = dict(zip(z["names"].tolist(), z["vecs"]))
    todo = [r["filename"] for r in rows if r["filename"] not in have]
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
    tokenizer = open_clip.get_tokenizer(MODEL_ID)
    model.eval()
    torch.set_num_threads(max(1, torch.get_num_threads()))
    with torch.no_grad():
        for i in range(0, len(todo), 16):
            batch, names = [], []
            for name in todo[i:i + 16]:
                try:
                    with Image.open(data / "images" / name) as im:
                        batch.append(preprocess(im.convert("RGB")))
                    names.append(name)
                except Exception as exc:  # unreadable download
                    print(f"  skip {name}: {exc}", flush=True)
            if not batch:
                continue
            f = model.encode_image(torch.stack(batch))
            f = f / f.norm(dim=-1, keepdim=True)
            for n, v in zip(names, f.numpy()):
                have[n] = v
            print(f"  embedded {min(i + 16, len(todo))}/{len(todo)}", flush=True)
            if (i // 16) % 10 == 9:
                np.savez(cache, names=np.array(list(have)), vecs=np.stack(list(have.values())))
        texts = {}
        for sp in KENYAN_MANGROVE_SPECIES:
            prompts = [f"a photo of {TAXONOMY[sp]}.", f"a photo of {sp}.", f"a photo of the mangrove {sp}."]
            t = model.encode_text(tokenizer(prompts))
            t = t / t.norm(dim=-1, keepdim=True)
            t = t.mean(0)
            texts[sp] = (t / t.norm()).numpy()
    np.savez(cache, names=np.array(list(have)), vecs=np.stack(list(have.values())))
    return have, texts


def decide(probs: np.ndarray, classes: list[str], declared: str, t_yes: float, t_no: float,
           trusted: set[str] | None = None) -> str:
    """yes if the declared species is likely; no if another species is clearly more likely.

    With `trusted`, "yes" is only ever given for species that met the accept bar
    on validation; for the rest a likely match becomes "unclear" (a person
    decides), while a clear mismatch is still disputed.
    """
    p_decl = probs[classes.index(declared)]
    top = int(np.argmax(probs))
    if classes[top] == declared and p_decl >= t_yes:
        return "yes" if trusted is None or declared in trusted else "unclear"
    if classes[top] != declared and probs[top] >= t_no:
        return "no"
    return "unclear"


def declarations(rows: list[dict], classes: list[str], seed: int) -> list[tuple[dict, str, bool]]:
    """Each photo twice: its true species, and one deliberately wrong species."""
    rnd = random.Random(seed)
    out = []
    for r in rows:
        out.append((r, r["species"], True))
        out.append((r, rnd.choice([c for c in classes if c != r["species"]]), False))
    return out


def score(pairs, probs_of, classes, t_yes, t_no, trusted=None) -> dict:
    res = defaultdict(int)
    for r, decl, correct in pairs:
        d = decide(probs_of[r["filename"]], classes, decl, t_yes, t_no, trusted)
        key = ("right_" if correct else "wrong_") + d
        res[key] += 1
    right = res["right_yes"] + res["right_no"] + res["right_unclear"]
    wrong = res["wrong_yes"] + res["wrong_no"] + res["wrong_unclear"]
    return {
        "accept": res["right_yes"] / right if right else 0.0,
        "false_dispute": res["right_no"] / right if right else 0.0,
        "catch": res["wrong_no"] / wrong if wrong else 0.0,
        "missed": res["wrong_yes"] / wrong if wrong else 0.0,
        "review": (res["right_unclear"] + res["wrong_unclear"]) / (right + wrong) if right + wrong else 0.0,
        "n_right": right, "n_wrong": wrong,
    }


def passes(m: dict) -> bool:
    return m["catch"] >= BAR["catch"] and m["accept"] >= BAR["accept"] and m["review"] <= BAR["review"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from sklearn.linear_model import LogisticRegression

    rows = load_manifest(args.data)
    print(f"{len(rows)} photos with images")
    vecs, texts = embed(args.data, rows, args.out / "embeddings.npz")
    rows = [r for r in rows if r["filename"] in vecs]
    by = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}
    classes = [c for c in KENYAN_MANGROVE_SPECIES if any(r["species"] == c for r in by["train"])]
    print("splits:", {s: len(v) for s, v in by.items()}, "| classes with training data:", len(classes))

    report: dict = {"model": MODEL_ID, "classes": classes, "bar": BAR, "splits": {s: len(v) for s, v in by.items()}}

    # ---- 2. zero-shot --------------------------------------------------------
    T = np.stack([texts[c] for c in classes])
    zs = {r["filename"]: int(np.argmax(vecs[r["filename"]] @ T.T)) for r in by["test"]}
    zs_acc = np.mean([classes[zs[r["filename"]]] == r["species"] for r in by["test"] if r["species"] in classes])
    report["zero_shot_test_top1"] = round(float(zs_acc), 3)
    print(f"\nzero-shot top-1 on test: {zs_acc:.1%}")

    # ---- 3. linear probe, C chosen on val ------------------------------------
    def xy(split):
        rs = [r for r in by[split] if r["species"] in classes]
        return np.stack([vecs[r["filename"]] for r in rs]), np.array([classes.index(r["species"]) for r in rs]), rs

    Xtr, ytr, _ = xy("train")
    Xva, yva, rva = xy("val")
    Xte, yte, rte = xy("test")
    best = None
    for C in (0.1, 0.3, 1, 3, 10, 30):
        clf = LogisticRegression(C=C, max_iter=5000, class_weight="balanced")
        clf.fit(Xtr, ytr)
        acc = (clf.predict(Xva) == yva).mean()
        print(f"  C={C:<5} val top-1 {acc:.1%}")
        if best is None or acc > best[1]:
            best = (C, acc, clf)
    C, val_acc, clf = best
    te_acc = float((clf.predict(Xte) == yte).mean())
    report.update({"probe_C": C, "probe_val_top1": round(float(val_acc), 3), "probe_test_top1": round(te_acc, 3)})
    print(f"probe: C={C}, val top-1 {val_acc:.1%}, TEST top-1 {te_acc:.1%}")

    # ---- 4. BlueProof decision; thresholds on val, one measurement on test ----
    probs_val = {r["filename"]: p for r, p in zip(rva, clf.predict_proba(Xva))}
    probs_te = {r["filename"]: p for r, p in zip(rte, clf.predict_proba(Xte))}
    pairs_val = declarations(rva, classes, seed=1)
    pairs_te = declarations(rte, classes, seed=2)

    grid = [round(x, 2) for x in np.arange(0.2, 0.96, 0.05)]
    # Choose for margin, not for a bare pass: the smallest slack across the three
    # criteria is maximised, on all of val and on its East African part, taking
    # the worse of the two. Iteration 1 picked the first passing pair on val with
    # no East African photos and lost six points of acceptance on test.
    rva_ea = [r for r in rva if r["east_africa"] == "1"]
    pairs_val_ea = declarations(rva_ea, classes, seed=5) if rva_ea else []

    def slack(m):
        return min(m["catch"] - BAR["catch"], m["accept"] - BAR["accept"], BAR["review"] - m["review"])

    candidates = []
    for t_yes in grid:
        for t_no in grid:
            m = score(pairs_val, probs_val, classes, t_yes, t_no)
            s = slack(m)
            if pairs_val_ea:
                s = min(s, slack(score(pairs_val_ea, probs_val, classes, t_yes, t_no)))
            candidates.append((passes(m), s, t_yes, t_no, m))
    candidates.sort(key=lambda c: (c[1], c[0]), reverse=True)
    ok, _, t_yes, t_no, m_val = candidates[0]
    m_test = score(pairs_te, probs_te, classes, t_yes, t_no)
    report.update({"thresholds": {"yes": t_yes, "no": t_no}, "val": m_val, "test": m_test,
                   "val_passes_bar": ok, "test_passes_bar": passes(m_test)})

    def line(name, m):
        return (f"{name:<22} accept {m['accept']:6.1%}  catch {m['catch']:6.1%}  review {m['review']:6.1%}"
                f"  missed {m['missed']:5.1%}  false-dispute {m['false_dispute']:5.1%}")

    print(f"\nthresholds chosen on val: yes>={t_yes}, no>={t_no}  (val meets bar: {ok})")
    print(line("val", m_val))
    if pairs_val_ea:
        print(line(f"val East Africa (n={len(rva_ea)})", score(pairs_val_ea, probs_val, classes, t_yes, t_no)))
    print(line("TEST (held out)", m_test))
    print(f"pilot bar: accept>={BAR['accept']:.0%}, catch>={BAR['catch']:.0%}, review<={BAR['review']:.0%}"
          f"  ->  TEST {'PASSES' if passes(m_test) else 'DOES NOT PASS'}")

    # Per-species trust, chosen on VAL only: a species may be auto-accepted
    # only if its validation acceptance met the bar with at least 5 photos.
    trusted = set()
    report["val_per_species"] = {}
    for c in classes:
        rs = [r for r in rva if r["species"] == c]
        if not rs:
            continue
        m = score(declarations(rs, classes, seed=6), probs_val, classes, t_yes, t_no)
        report["val_per_species"][c] = {"n": len(rs), "accept": round(m["accept"], 3)}
        if len(rs) >= 5 and m["accept"] >= BAR["accept"]:
            trusted.add(c)
    report["trusted_species"] = sorted(trusted)
    m_test_trusted = score(pairs_te, probs_te, classes, t_yes, t_no, trusted)
    report["test_with_trust"] = m_test_trusted
    print(f"\ntrusted for auto-accept (from val): {sorted(trusted)}")
    print(line("TEST with trust list", m_test_trusted))
    if ea := [r for r in rte if r["east_africa"] == "1"]:
        m = score(declarations(ea, classes, seed=4), probs_te, classes, t_yes, t_no, trusted)
        report["test_east_africa_with_trust"] = {"n": len(ea), **m}
        print(line(f"East Africa, trust (n={len(ea)})", m))

    # Per species and East Africa, on test.
    report["test_per_species"] = {}
    print("\nper species (test):")
    for c in classes:
        rs = [r for r in rte if r["species"] == c]
        if not rs:
            print(f"  {c:<24} no test photos")
            continue
        m = score(declarations(rs, classes, seed=3), probs_te, classes, t_yes, t_no)
        top1 = float(np.mean([classes[int(np.argmax(probs_te[r['filename']]))] == c for r in rs]))
        report["test_per_species"][c] = {"n": len(rs), "top1": round(top1, 3), **{k: round(v, 3) if isinstance(v, float) else v for k, v in m.items()}}
        print(f"  {c:<24} n={len(rs):<3} top-1 {top1:5.1%}  accept {m['accept']:5.1%}  catch {m['catch']:5.1%}  review {m['review']:5.1%}")
    ea = [r for r in rte if r["east_africa"] == "1"]
    if ea:
        m = score(declarations(ea, classes, seed=4), probs_te, classes, t_yes, t_no)
        report["test_east_africa"] = {"n": len(ea), **m}
        print(line(f"East Africa (n={len(ea)})", m))

    # Save the probe: small, CPU-only, reproducible.
    np.savez(args.out / "species_probe.npz", coef=clf.coef_, intercept=clf.intercept_,
             classes=np.array(classes), t_yes=t_yes, t_no=t_no, trusted=np.array(sorted(trusted)))
    (args.out / "report.json").write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(f"\nsaved {args.out / 'species_probe.npz'} and report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
