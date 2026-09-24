"""Bounded assessment of a plot photograph by a vision language model.

The model is asked four questions, in the order of how far its answers can be
trusted (paper, section 4.4):

  (a) Is this image legible enough to assess?
  (b) What condition is visible? healthy | stressed | dead | unclear
  (c) Is there evidence of cutting or pest damage?
  (d) Is the monitor's DECLARED species consistent with the image?

It is never asked to name the species from scratch. Published evidence puts
general purpose VLM fabrication of species names at 5.9 to 9.6 percent on field
imagery, so the model corroborates the person standing at the plot rather than
overruling them, and any label outside the nine Kenyan species is coerced to
"unclear".

NDVI and every other piece of arithmetic live in deterministic code
(services/sentinel.py, services/gate.py). The model's output is advisory input
to a gate, never a decision.

`build_messages` and `parse_reply` are shared with tools/llama_eval.py, so the
evaluation measures exactly the prompt that is deployed.

With LLAMA_API_URL unset, a deterministic mock stands in so the flow demos
offline. Its verdicts are labelled "mock" all the way into the ledger.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re

from ..config import settings
from ..schemas import Verdict
from . import http

# Bumped whenever the wording below changes. Recorded with every verdict, so a
# figure measured against one prompt is never silently credited to another.
PROMPT_VERSION = "v2-bounded"

KENYAN_MANGROVE_SPECIES = [
    "Rhizophora mucronata",
    "Avicennia marina",
    "Ceriops tagal",
    "Sonneratia alba",
    "Bruguiera gymnorrhiza",
    "Xylocarpus granatum",
    "Xylocarpus moluccensis",
    "Lumnitzera racemosa",
    "Heritiera littoralis",
]

HEALTH = {"healthy", "stressed", "dead", "unclear"}

SYSTEM_PROMPT = (
    "You are assisting a human verifier for a community mangrove restoration "
    "project on the Kenyan coast. You will see one photograph of a monitoring "
    "plot and the species the community monitor says is planted there. Report "
    "only what is visible. Do not guess.\n\n"
    "Answer these questions in order:\n"
    "1. legible: is the image sharp, lit and framed well enough to judge the "
    "plants? true or false.\n"
    "2. health: the overall condition of the seedlings visible: healthy, "
    "stressed, dead, or unclear.\n"
    "3. cutting: is there visible evidence of cutting (stumps, cut poles, axe "
    "marks)? true or false. pests: is there visible pest damage (boring holes, "
    "frass, dieback)? true or false.\n"
    "4. species_consistent: is the image consistent with the DECLARED species? "
    "yes, no, or unclear. Young mangroves of different species can look alike; "
    "say unclear unless the evidence is plain. Only if you answer no, give "
    "species_if_different chosen from exactly this list, or unclear: "
    f"{', '.join(KENYAN_MANGROVE_SPECIES)}.\n"
    "5. seedlings: how many seedlings are clearly visible (integer).\n"
    "6. confidence: 0 to 1, how confident you are in answers 1 to 4 together.\n"
    "7. reasoning: one or two sentences on what you saw.\n\n"
    "Reply with ONLY a JSON object with keys legible, health, cutting, pests, "
    "species_consistent, species_if_different, seedlings, confidence, reasoning."
)


class VerifierError(Exception):
    """The model could not be reached or did not answer in the agreed shape."""


def build_messages(image_bytes: bytes, declared_species: str | None, mime: str = "image/jpeg") -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode()
    declared = declared_species or "not stated"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Declared species: {declared}. Assess this monitoring plot photograph."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        },
    ]


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise VerifierError("model reply contained no JSON object")
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerifierError(f"model reply was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VerifierError("model reply was not a JSON object")
    return data


def _as_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "yes", "1"}
    return bool(v)


def _canon_species(name) -> str | None:
    n = str(name or "").strip().lower()
    for s in KENYAN_MANGROVE_SPECIES:
        if s.lower() == n:
            return s
    return None


def parse_reply(content: str, declared_species: str | None, source: str) -> Verdict:
    """Turn a model reply into a Verdict, coercing anything off-menu to unclear."""
    data = _extract_json(content)

    health = str(data.get("health", "unclear")).strip().lower()
    if health not in HEALTH:
        health = "unclear"

    consistent = str(data.get("species_consistent", "unclear")).strip().lower()
    if consistent not in {"yes", "no", "unclear"}:
        consistent = "unclear"

    declared = _canon_species(declared_species)
    if consistent == "yes" and declared:
        detected = declared
    elif consistent == "no":
        # A disagreement names an alternative from the closed set or nothing.
        detected = _canon_species(data.get("species_if_different")) or "unclear"
    else:
        detected = "unclear"

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    try:
        seedlings = max(0, int(data.get("seedlings", 0) or 0))
    except (TypeError, ValueError):
        seedlings = 0

    return Verdict(
        source=source,
        legible=_as_bool(data.get("legible", False)),
        species_consistent=consistent,
        detected_species=detected,
        seedlings_visible=seedlings,
        health=health,
        evidence_of_cutting=_as_bool(data.get("cutting", False)),
        pest_damage=_as_bool(data.get("pests", False)),
        confidence=confidence,
        # No cheerful default. If the model returned nothing here, the record
        # should say the model returned nothing here.
        reasoning=str(data.get("reasoning", "") or "No reasoning returned."),
    )


def _mock_verdict(seed: str, declared_species: str | None) -> Verdict:
    """Deterministic stand in so the flow runs with no credentials.

    It agrees with the declared species most of the time and disputes it
    occasionally, which is the shape a working corroborator would have. It says
    "mock" about itself in every field that leaves this function.
    """
    d = hashlib.sha256(seed.encode()).digest()
    declared = _canon_species(declared_species)
    dispute = declared is not None and d[0] % 10 == 0
    if declared and not dispute:
        consistent, species = "yes", declared
    elif dispute:
        others = [s for s in KENYAN_MANGROVE_SPECIES if s != declared]
        consistent, species = "no", others[d[1] % len(others)]
    else:
        consistent, species = "unclear", "unclear"
    seedlings = 3 + (d[2] % 18)
    health = ["healthy", "healthy", "healthy", "stressed", "unclear"][d[3] % 5]
    cutting = (d[4] % 10) == 0
    pests = species == "Sonneratia alba" and (d[5] % 3 == 0)
    confidence = round(0.55 + (d[6] % 44) / 100, 2)
    return Verdict(
        source="mock",
        legible=True,
        species_consistent=consistent,
        detected_species=species,
        seedlings_visible=seedlings,
        health=health,
        evidence_of_cutting=cutting,
        pest_damage=pests,
        confidence=confidence,
        reasoning=(
            f"Mock verifier, not a model: {seedlings} seedlings, condition {health}, "
            f"declared species {consistent}."
            + (" Cut stumps present." if cutting else "")
            + (" Boring damage on stems." if pests else "")
        ),
    )


def is_live() -> bool:
    return bool(settings.llama_api_url)


def source_label() -> str:
    if not is_live():
        return "mock"
    n = max(1, settings.verifier_samples)
    return f"{settings.llama_model}@{PROMPT_VERSION}" + (f"x{n}" if n > 1 else "")


async def _chat(messages: list[dict], temperature: float, max_tokens: int = 400) -> str:
    payload = {
        "model": settings.llama_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {settings.llama_api_key}"} if settings.llama_api_key else {}
    try:
        async with http.client(settings.llama_timeout_s) as client:
            resp = await client.post(settings.llama_api_url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
    except Exception as exc:  # network, HTTP status, or an unexpected body
        raise VerifierError(f"{type(exc).__name__}: {exc}") from exc


# ---- Confidence from agreement ----------------------------------------------
#
# A vision model's self-reported confidence is a number it writes, not a
# measurement, and it is the number that gates payment. So the question is
# asked several times at a non-zero temperature, and confidence becomes the
# share of answers that agree on the things the gate acts on: legibility,
# condition and species consistency. The self-reported figure is kept beside it
# for the calibration study, but no longer decides anything.


def aggregate(verdicts: list[Verdict], source: str) -> Verdict:
    """Combine sampled verdicts. Pure, and shared with tools/llama_eval.py."""
    if not verdicts:
        raise VerifierError("no usable samples")
    if len(verdicts) == 1:
        v = verdicts[0]
        return v.model_copy(update={"source": source, "self_reported_confidence": v.confidence, "samples": 1})

    def key(v: Verdict) -> tuple:
        return (v.legible, v.health, v.species_consistent)

    counts: dict[tuple, int] = {}
    for v in verdicts:
        counts[key(v)] = counts.get(key(v), 0) + 1
    # Most common answer; on a tie, the more cautious one (not "yes", not legible).
    modal = max(counts, key=lambda k: (counts[k], k[2] != "yes", not k[0]))
    agreeing = [v for v in verdicts if key(v) == modal]
    agreement = counts[modal] / len(verdicts)

    alternatives = [v.detected_species for v in agreeing]
    detected = max(sorted(set(alternatives)), key=alternatives.count)
    seedlings = sorted(v.seedlings_visible for v in agreeing)[len(agreeing) // 2]
    return Verdict(
        source=source,
        legible=modal[0],
        health=modal[1],
        species_consistent=modal[2],
        detected_species=detected,
        seedlings_visible=seedlings,
        # Recall first, as the paper specifies: one sample seeing a stump is
        # enough to put the plot on the alerts list. It does not block payment.
        evidence_of_cutting=any(v.evidence_of_cutting for v in verdicts),
        pest_damage=any(v.pest_damage for v in verdicts),
        confidence=round(agreement, 3),
        self_reported_confidence=round(sum(v.confidence for v in agreeing) / len(agreeing), 3),
        samples=len(verdicts),
        reasoning=agreeing[0].reasoning
        + ("" if agreement == 1 else f" ({counts[modal]} of {len(verdicts)} samples agreed.)"),
    )


async def verify_plot(
    image_bytes: bytes, declared_species: str | None, mime: str = "image/jpeg"
) -> Verdict:
    """Assess a plot photograph. Raises VerifierError if the live model fails.

    There is no text-only path. An assessment of something other than the
    photograph is not evidence, so it is not offered.
    """
    if not is_live():
        return _mock_verdict(hashlib.sha256(image_bytes).hexdigest(), declared_species)

    n = max(1, settings.verifier_samples)
    messages = build_messages(image_bytes, declared_species, mime)
    # One sample is deterministic; several need variation to mean anything.
    temperature = 0.0 if n == 1 else settings.verifier_sample_temperature
    results = await asyncio.gather(*[_chat(messages, temperature) for _ in range(n)], return_exceptions=True)

    verdicts, errors = [], []
    for r in results:
        if isinstance(r, BaseException):
            errors.append(r)
            continue
        try:
            verdicts.append(parse_reply(r, declared_species, source_label()))
        except VerifierError as exc:
            errors.append(exc)
    # A majority of samples must answer, or the agreement figure means nothing.
    if not verdicts or (n > 1 and len(verdicts) * 2 <= n):
        raise VerifierError(f"only {len(verdicts)} of {n} samples usable: {errors[0] if errors else ''}")
    return aggregate(verdicts, source_label())


# ---- Plot marker ---------------------------------------------------------------
#
# The protocol's first shot is the plot marker. Reading printed or painted text
# is among the more reliable things a vision model does, and it answers a
# question GPS cannot: is this photograph of THIS plot. The model only reads;
# comparing the reading with the plot code is done in code (services/gate.py).

MARKER_PROMPT = (
    "This photograph shows a plot marker (a post, board or tag) in a mangrove "
    "restoration site. Read the plot code written on it exactly as written, for "
    "example TC-A-014. Do not guess characters you cannot see. Reply with ONLY a "
    'JSON object: {"legible": true or false, "code": "the code, or null"}.'
)


def parse_marker(content: str) -> dict:
    data = _extract_json(content)
    code = data.get("code")
    code = str(code).strip() if code not in (None, "", "null") else None
    return {"legible": _as_bool(data.get("legible", False)) and code is not None, "code": code}


def marker_messages(image_bytes: bytes, mime: str = "image/jpeg") -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode()
    return [
        {"role": "system", "content": MARKER_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Read the plot code on this marker."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]},
    ]


async def read_marker(image_bytes: bytes, expected_code: str, mime: str = "image/jpeg") -> dict:
    """Return {legible, code, source}. Raises VerifierError on a live failure."""
    if not is_live():
        # The mock cannot read. It echoes the expected code and says so.
        return {"legible": True, "code": expected_code, "source": "mock"}
    content = await _chat(marker_messages(image_bytes, mime), temperature=0.0, max_tokens=80)
    return {**parse_marker(content), "source": f"{settings.llama_model}@{PROMPT_VERSION}"}


# ---- Comparison with the previous visit -----------------------------------------
#
# The previous verified photograph of the plot and today's are stitched side by
# side into ONE image (services/photos.side_by_side), because several Llama
# vision models are only reliable with a single image per request. The model is
# asked whether it is the same place and what changed. "Not the same place"
# sends the submission to a person; the change itself is recorded, never paid
# on, which keeps the incentive where the paper puts it.

COMPARE_PROMPT = (
    "The image has two photographs of a mangrove monitoring plot side by side. "
    "LEFT is the previous verified visit; RIGHT is today. Compare only what is "
    "visible.\n"
    "1. same_location: do they show the same place (same shoreline, roots, "
    "marker, background)? yes, no, or unclear. Seedlings grow and die, so judge "
    "by the setting, not the plants.\n"
    "2. change: the plants since the previous visit: improved, unchanged, "
    "declined, or unclear.\n"
    "3. note: one sentence on the most important difference.\n"
    "Reply with ONLY a JSON object with keys same_location, change, note."
)


def parse_comparison(content: str) -> dict:
    data = _extract_json(content)
    same = str(data.get("same_location", "unclear")).strip().lower()
    change = str(data.get("change", "unclear")).strip().lower()
    return {
        "same_location": same if same in {"yes", "no", "unclear"} else "unclear",
        "change": change if change in {"improved", "unchanged", "declined", "unclear"} else "unclear",
        "note": str(data.get("note", "") or "")[:500],
    }


def compare_messages(stitched_jpeg: bytes) -> list[dict]:
    b64 = base64.b64encode(stitched_jpeg).decode()
    return [
        {"role": "system", "content": COMPARE_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Compare the previous visit (left) with today (right)."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]},
    ]


async def compare_visits(stitched_jpeg: bytes) -> dict:
    """Return {same_location, change, note, source}. Raises VerifierError on a live failure."""
    if not is_live():
        return {"same_location": "yes", "change": "unclear",
                "note": "Mock comparison, not a model.", "source": "mock"}
    content = await _chat(compare_messages(stitched_jpeg), temperature=0.0, max_tokens=200)
    return {**parse_comparison(content), "source": f"{settings.llama_model}@{PROMPT_VERSION}"}
