"""Specialist species check: BioCLIP image features + a trained linear probe.

Off unless SPECIES_CLASSIFIER_PATH points at a species_probe.npz produced by
tools/classifier.py. When on, it answers the species question in place of the
vision-language model, which on 2026-09-24 could not tell the nine Kenyan
species apart (docs/evaluations/). Llama still answers legibility, condition,
cutting, pests and the marker.

Heavy dependencies (torch, open_clip) are imported only when enabled, so the
API image stays small for deployments that do not use it.
"""
from __future__ import annotations

import hashlib
import io
import threading
from pathlib import Path

import numpy as np

from ..config import settings

MODEL_ID = "hf-hub:imageomics/bioclip"

_lock = threading.Lock()
_state: dict = {}


class ClassifierError(Exception):
    pass


def is_enabled() -> bool:
    return bool(settings.species_classifier_path)


def _load() -> dict:
    with _lock:
        if _state:
            return _state
        path = Path(settings.species_classifier_path)
        if not path.exists():
            raise ClassifierError(f"species probe not found at {path}")
        # Plain numeric and string arrays only; pickled objects are never loaded.
        z = np.load(path, allow_pickle=False)
        import open_clip
        import torch

        model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
        model.eval()
        _state.update(
            model=model, preprocess=preprocess, torch=torch,
            coef=z["coef"], intercept=z["intercept"], classes=[str(c) for c in z["classes"]],
            t_yes=float(z["t_yes"]), t_no=float(z["t_no"]),
            # Species that met the accept bar on validation; others are never
            # auto-accepted. Probes without the field trust every species.
            trusted=set(str(c) for c in z["trusted"]) if "trusted" in z.files else None,
            version="bioclip-probe@" + hashlib.sha256(path.read_bytes()).hexdigest()[:10],
        )
        return _state


def label() -> str:
    return _load()["version"] if is_enabled() else "off"


def probabilities(image_bytes: bytes) -> dict[str, float]:
    from PIL import Image

    s = _load()
    with Image.open(io.BytesIO(image_bytes)) as im:
        x = s["preprocess"](im.convert("RGB")).unsqueeze(0)
    with s["torch"].no_grad():
        f = s["model"].encode_image(x)
        f = (f / f.norm(dim=-1, keepdim=True)).numpy()[0]
    logits = s["coef"] @ f + s["intercept"]
    p = np.exp(logits - logits.max())
    p = p / p.sum()
    return dict(zip(s["classes"], p.tolist()))


def check(image_bytes: bytes, declared: str | None) -> dict:
    """{consistent: yes|no|unclear, detected, probability, source}.

    The same decision rule tools/classifier.py measured: yes if the declared
    species is the top class above t_yes; no if another species is top above
    t_no; otherwise unclear, which sends the submission to a person.
    """
    try:
        probs = probabilities(image_bytes)
    except ClassifierError:
        raise
    except Exception as exc:  # corrupt image, model load failure
        raise ClassifierError(f"{type(exc).__name__}: {exc}") from exc
    s = _load()
    top = max(probs, key=probs.get)
    if declared not in probs:
        return {"consistent": "unclear", "detected": top, "probability": probs[top], "source": s["version"]}
    if top == declared and probs[declared] >= s["t_yes"]:
        use_trust = settings.species_trust_list and s["trusted"] is not None
        consistent = "yes" if not use_trust or declared in s["trusted"] else "unclear"
    elif top != declared and probs[top] >= s["t_no"]:
        consistent = "no"
    else:
        consistent = "unclear"
    return {"consistent": consistent, "detected": top, "probability": round(probs[top], 3), "source": s["version"]}
