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


def fetch(client: httpx.Client, species: str, limit: int) -> list[dict]:
    rows, page = [], 1
    while len(rows) < limit:
        r = client.get(API, params={
            "taxon_name": species, "quality_grade": "research", "photo_license": LICENCES,
            "per_page": 100, "page": page, "order_by": "id", "order": "asc",
        })
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            break
        for obs in results:
            lat = lon = None
            if obs.get("location"):
                lat, lon = (float(x) for x in obs["location"].split(","))
            for p in obs.get("photos", [])[:2]:  # at most 2 photos per observation
                if (p.get("license_code") or "") not in LICENCES.split(","):
                    continue
                rows.append({
                    "species": species,
                    "observation_id": obs["id"],
                    "photo_id": p["id"],
                    "url": p["url"].replace("square", "medium"),  # ~500 px
                    "licence": p["license_code"],
                    "attribution": p.get("attribution", ""),
                    "lat": lat, "lon": lon,
                    "east_africa": int(in_east_africa(lat, lon)),
                })
        page += 1
        time.sleep(1.1)  # iNaturalist asks for about one request per second
    return rows[:limit]


def split(rows: list[dict], seed: int = 7) -> None:
    """Assign train/val/test by observation. East African observations go to test."""
    obs = sorted({r["observation_id"] for r in rows})
    ea = {r["observation_id"] for r in rows if r["east_africa"]}
    rest = [o for o in obs if o not in ea]
    random.Random(seed).shuffle(rest)
    n = len(rest)
    # Test gets East Africa plus enough elsewhere to reach ~20%; val ~15%.
    need_test = max(0, round(0.20 * len(obs)) - len(ea))
    test = ea | set(rest[:need_test])
    val = set(rest[need_test:need_test + round(0.15 * n)])
    for r in rows:
        o = r["observation_id"]
        r["split"] = "test" if o in test else "val" if o in val else "train"


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
