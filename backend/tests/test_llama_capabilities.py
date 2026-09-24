"""Marker reading, comparison with the previous visit, confidence by agreement."""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app.config import settings
from app.schemas import Verdict
from app.services import llama_vision
from conftest import GOOD, model_router, photo, submit


@pytest.fixture
def live(monkeypatch):
    # Restored after each test; model_router sets them for the test's duration.
    monkeypatch.setattr(settings, "llama_api_url", None)
    monkeypatch.setattr(settings, "llama_api_key", None)
    return model_router


def submit_with_marker(client, headers, img, marker_img, **form):
    data = {"plot_id": "1", "lat": "-4.01815", "lon": "39.66410", **form}
    files = {"image": ("plot.jpg", img, "image/jpeg"), "marker": ("marker.jpg", marker_img, "image/jpeg")}
    return client.post("/monitoring/submit-photo", data=data, files=files, headers=headers)


# ---- confidence from agreement -------------------------------------------------


def v(consistent="yes", health="healthy", legible=True, conf=0.9, cutting=False, seedlings=10):
    return Verdict(source="t", legible=legible, species_consistent=consistent, detected_species="X",
                   seedlings_visible=seedlings, health=health, evidence_of_cutting=cutting,
                   pest_damage=False, confidence=conf, reasoning="r")


def test_aggregate_uses_agreement_not_self_report():
    out = llama_vision.aggregate([v(conf=0.99), v(conf=0.99), v(consistent="no", conf=0.99)], "m")
    assert out.species_consistent == "yes"
    assert out.confidence == pytest.approx(0.667, abs=0.001)
    assert out.self_reported_confidence == pytest.approx(0.99)
    assert out.samples == 3


def test_aggregate_tie_breaks_towards_caution():
    out = llama_vision.aggregate([v(consistent="yes"), v(consistent="unclear")], "m")
    assert out.species_consistent == "unclear"
    assert out.confidence == 0.5


def test_aggregate_flags_cutting_if_any_sample_saw_it():
    out = llama_vision.aggregate([v(), v(), v(cutting=True)], "m")
    assert out.evidence_of_cutting is True


def test_split_samples_escalate_even_when_each_sounds_certain(client, amina, live):
    live(verify_sequence=[
        {**GOOD, "confidence": 0.95},
        {**GOOD, "species_consistent": "no", "species_if_different": "Ceriops tagal", "confidence": 0.95},
        {**GOOD, "species_consistent": "unclear", "confidence": 0.95},
    ])
    ev = submit(client, amina, photo(40), client_ref="s-1").json()["event"]
    assert ev["status"] == "needs_human"
    assert ev["confidence"] < settings.min_verification_confidence
    assert ev["self_reported_confidence"] == pytest.approx(0.95)
    assert ev["verifier_samples"] == 3


def test_samples_run_warm_and_majority_must_answer(client, amina, live):
    seen = live(verify=GOOD, verify_sequence=[GOOD, 500, 500])
    ev = submit(client, amina, photo(41), client_ref="s-2").json()["event"]
    assert all(b["temperature"] == settings.verifier_sample_temperature for b in seen["verify"])
    assert ev["status"] == "needs_human" and ev["verification_source"].startswith("error:")


# ---- plot marker ---------------------------------------------------------------


def test_marker_matching_plot_is_verified(client, amina, live):
    seen = live(verify=GOOD, marker={"legible": True, "code": "tc-a 001"})
    ev = submit_with_marker(client, amina, photo(50), photo(51), client_ref="m-1").json()["event"]
    assert ev["status"] == "verified"
    assert ev["marker_code_read"] == "tc-a 001" and ev["marker_matches"] is True
    assert len(seen["marker"]) == 1 and ev["marker_sha256"]


def test_marker_for_another_plot_escalates(client, amina, live):
    live(verify=GOOD, marker={"legible": True, "code": "TC-B-007"})
    ev = submit_with_marker(client, amina, photo(52), photo(53), client_ref="m-2").json()["event"]
    assert ev["status"] == "needs_human"
    assert any("marker reads TC-B-007, not TC-A-001" in r for r in ev["review_reasons"])


def test_unreadable_marker_is_recorded_not_blocking(client, amina, live):
    live(verify=GOOD, marker={"legible": False, "code": None})
    ev = submit_with_marker(client, amina, photo(54), photo(55), client_ref="m-3").json()["event"]
    assert ev["status"] == "verified" and ev["marker_matches"] is None


def test_marker_can_be_required(client, amina, live, monkeypatch):
    monkeypatch.setattr(settings, "require_marker", True)
    live(verify=GOOD)
    ev = submit(client, amina, photo(56), client_ref="m-4").json()["event"]
    assert any("No plot marker" in r for r in ev["review_reasons"])


# ---- comparison with the previous visit -----------------------------------------


def test_different_place_from_last_visit_escalates(client, amina, live, monkeypatch):
    monkeypatch.setattr(settings, "min_days_between_paid_events", 0)
    seen = live(verify=GOOD, compare={"same_location": "no", "change": "unclear", "note": "Different shoreline."})
    first = submit(client, amina, photo(60), client_ref="c-1").json()["event"]
    assert first["status"] == "verified" and first["previous_event_id"] is None
    assert seen["compare"] == []  # nothing to compare against yet

    second = submit(client, amina, photo(61), client_ref="c-2").json()["event"]
    assert second["previous_event_id"] == first["id"]
    assert second["same_location"] == "no" and second["status"] == "needs_human"
    assert any("same place" in r for r in second["review_reasons"])

    # One stitched image, wider than either photo: works on single-image models.
    content = seen["compare"][0]["messages"][-1]["content"]
    images = [c for c in content if c["type"] == "image_url"]
    assert len(images) == 1
    stitched = Image.open(io.BytesIO(base64.b64decode(images[0]["image_url"]["url"].split(",")[1])))
    assert stitched.width > 2 * stitched.height


def test_same_place_records_change_without_affecting_pay(client, amina, live, monkeypatch):
    monkeypatch.setattr(settings, "min_days_between_paid_events", 0)
    live(verify=GOOD, compare={"same_location": "yes", "change": "declined", "note": "Fewer seedlings."})
    submit(client, amina, photo(62), client_ref="c-3")
    ev = submit(client, amina, photo(63), client_ref="c-4").json()["event"]
    # Decline is recorded; paying for reporting, not survival, means it is still paid.
    assert ev["change_vs_previous"] == "declined" and ev["status"] == "verified"


def test_comparison_failure_does_not_block(client, amina, live, monkeypatch):
    monkeypatch.setattr(settings, "min_days_between_paid_events", 0)
    live(verify=GOOD, compare="not json at all")
    submit(client, amina, photo(64), client_ref="c-5")
    ev = submit(client, amina, photo(65), client_ref="c-6").json()["event"]
    assert ev["same_location"] == "unclear" and ev["status"] == "verified"
