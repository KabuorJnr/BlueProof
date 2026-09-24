#!/usr/bin/env python3
"""Build a labelled mangrove photo dataset from iNaturalist research-grade observations.

Writes a manifest CSV; downloads nothing unless --download is given.

Why iNaturalist: "research grade" means the species has been confirmed by
community identifiers, which is a far better label than a Wikimedia category.
It is still not a field determination at a BlueProof plot, so a model trained
here must be tested on Tudor Creek photos before it gates any payment.

Splits are by observation (never by photo), so two photos of the same tree
cannot land on both sides. Observations from the East African coast are held
out as the test split whenever there are any: the question that matters is
how a model does on Kenyan-type imagery it never trained on.

    python tools/build_dataset.py --out data/dataset --per-species 150
    python tools/build_dataset.py --out data/dataset --per-species 150 --download

Every photo keeps its licence and attribution in the manifest. CC BY and
CC BY-SA require attribution if images are redistributed; do not commit the
images themselves to a public repository.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.llama_vision import KENYAN_MANGROVE_SPECIES  # noqa: E402

API = "https://api.inaturalist.org/v1/observations"
UA = {"User-Agent": "BlueProofDataset/0.1 (https://github.com/KabuorJnr/BlueProof)"}
LICENCES = "cc0,cc-by,cc-by-sa"
EAST_AFRICA = {"swlat": -27, "swlng": 32, "nelat": 5, "nelng": 52}  # Somalia to Mozambique


def in_east_africa(lat, lon) -> bool:
    return (lat is not None and lon is not None
            and EAST_AFRICA["swlat"] <= lat <= EAST_AFRICA["nelat"]
            and EAST_AFRICA["swlng"] <= lon <= EAST_AFRICA["nelng"])


def _page(client: httpx.Client, species: str, page: int, extra: dict) -> list[dict]:
    r = client.get(API, params={
        "taxon_name": species, "quality_grade": "research", "photo_license": LICENCES,
        "per_page": 100, "page": page, "order_by": "id", "order": "asc", **extra,
    })
    r.raise_for_status()
    time.sleep(1.1)  # iNaturalist asks for about one request per second
    return r.json().get("results", [])


def _rows(species: str, obs: dict) -> list[dict]:
    lat = lon = None
    if obs.get("location"):
        lat, lon = (float(x) for x in obs["location"].split(","))
    out = []
    for p in obs.get("photos", [])[:2]:  # at most 2 photos per observation
        if (p.get("license_code") or "") not in LICENCES.split(","):
            continue
        out.append({
            "species": species,
            "observation_id": obs["id"],
            "photo_id": p["id"],
            "url": p["url"].replace("square", "medium"),  # ~500 px
            "licence": p["license_code"],
            "attribution": p.get("attribution", ""),
            "lat": lat, "lon": lon,
            "east_africa": int(in_east_africa(lat, lon)),
        })
    return out


def fetch(client: httpx.Client, species: str, limit: int) -> list[dict]:
    """East African observations first (all of them), then the rest up to `limit`.

    The East African ones are few and are the test set, so they must never be
    lost to the cap.
    """
    rows: list[dict] = []
    seen: set[int] = set()
    for extra in (EAST_AFRICA, {}):
        page = 1
        while True:
            if extra == {} and len(rows) >= limit:
                break
            results = _page(client, species, page, extra)
            if not results:
                break
            for obs in results:
                if obs["id"] in seen:
                    continue
                seen.add(obs["id"])
                rows += _rows(species, obs)
            page += 1
    ea = [r for r in rows if r["east_africa"]]
    rest = [r for r in rows if not r["east_africa"]]
    return ea + rest[: max(0, limit - len(ea))]


def split(rows: list[dict], seed: int = 7, ea_to_val: float = 0.5) -> None:
    """Assign train/val/test by observation, per species.

    East African observations never go to train. `ea_to_val` of them go to
    val, so decision thresholds are tuned on Kenyan-type imagery; the rest are
    test. (Iteration 1 put them all in test: val never saw the region, and the
    thresholds it chose did not transfer.)

    Stratified so that a rare species (a dozen observations) still gets at
    least one test and one validation observation when it can spare them.
    """
    rnd = random.Random(seed)
    assign: dict[int, str] = {}
    for sp in sorted({r["species"] for r in rows}):
        obs = sorted({r["observation_id"] for r in rows if r["species"] == sp})
        ea = [o for o in obs if any(r["east_africa"] for r in rows if r["observation_id"] == o)]
        rnd.shuffle(ea)
        ea_val = ea[: round(ea_to_val * len(ea))]
        ea_test = ea[len(ea_val):]
        rest = [o for o in obs if o not in ea]
        rnd.shuffle(rest)
        n = len(obs)
        n_test = max(len(ea_test), round(0.20 * n), 1 if n >= 3 else 0)
        n_val = max(len(ea_val), round(0.15 * n), 1 if n >= 4 else 0)
        extra_test = max(0, n_test - len(ea_test))
        extra_val = max(0, n_val - len(ea_val))
        for o in ea_test + rest[:extra_test]:
            assign[o] = "test"
        for o in ea_val + rest[extra_test:extra_test + extra_val]:
            assign[o] = "val"
        for o in rest[extra_test + extra_val:]:
            assign[o] = "train"
    for r in rows:
        r["split"] = assign[r["observation_id"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-species", type=int, default=150)
    ap.add_argument("--download", action="store_true", help="also download the images")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = args.out / "manifest.csv"
    rows: list[dict] = []
    with httpx.Client(timeout=90, headers=UA) as client:
        for sp in KENYAN_MANGROVE_SPECIES:
            got = fetch(client, sp, args.per_species)
            print(f"{sp:<26} {len(got):>4} photos, {sum(r['east_africa'] for r in got):>3} East African", flush=True)
            rows += got
        split(rows)
        for r in rows:
            r["filename"] = f"{r['species'].replace(' ', '_')}_{r['photo_id']}.jpg"
        with manifest.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nmanifest: {manifest}  ({len(rows)} photos)")
        for s in ("train", "val", "test"):
            print(f"  {s:<5} {sum(r['split'] == s for r in rows)}")

        if args.download:
            img_dir = args.out / "images"
            img_dir.mkdir(exist_ok=True)
            for i, r in enumerate(rows, 1):
                path = img_dir / r["filename"]
                if path.exists():
                    continue
                try:
                    resp = client.get(r["url"], follow_redirects=True)
                    resp.raise_for_status()
                    path.write_bytes(resp.content)
                except Exception as exc:
                    print(f"  [{i}] {r['filename']}: {exc}", flush=True)
                if i % 50 == 0:
                    print(f"  downloaded {i}/{len(rows)}", flush=True)
                time.sleep(0.3)

    # Eval-compatible labels per split, for tools/llama_eval.py.
    for s in ("train", "val", "test"):
        with (args.out / f"labels_{s}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "species", "health", "cutting", "pests"])
            for r in rows:
                if r["split"] == s:
                    w.writerow([r["filename"], r["species"], "", "", ""])
    print("fingerprint:", hashlib.sha256(manifest.read_bytes()).hexdigest()[:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
