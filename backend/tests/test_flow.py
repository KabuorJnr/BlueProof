"""End to end: submit, gate, pay, review, ledger."""
from __future__ import annotations

from conftest import GOOD, PLOT, photo, submit


def test_root_reports_modes(client):
    r = client.get("/").json()
    assert r["llama"] == "mock" and r["mpesa"] == "mock" and r["satellite"] == "mock"


def test_submission_requires_sign_in(client):
    assert submit(client, {}, photo(1)).status_code == 401


def test_verified_submission_pays_and_writes_ledger(client, amina, live_model):
    seen = live_model(GOOD)
    r = submit(client, amina, photo(1), client_ref="a-1")
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["event"]["status"] == "verified"
    assert body["payment"]["status"] == "success"
    assert "phone" not in body["payment"]
    # The declared species went to the model; the model was not asked to name it.
    user_text = next(c["text"] for c in seen[0]["messages"][-1]["content"] if c["type"] == "text")
    assert "Declared species: Rhizophora mucronata" in user_text

    ledger = client.get("/ledger").json()
    assert len(ledger) == 1
    assert ledger[0]["monitor_ref"] == "BP-M-0001"
    assert ledger[0]["species"] == PLOT["species"]
    assert ledger[0]["photo_sha256"] == body["event"]["photo_sha256"]
    assert ledger[0]["verification_source"].endswith("@v3-boundedx3")
    assert "Amina" not in str(ledger)
    assert client.get("/ledger/verify").json()["ok"] is True


def test_retry_with_same_client_ref_is_idempotent(client, amina, live_model):
    live_model(GOOD)
    first = submit(client, amina, photo(1), client_ref="a-1").json()
    again = submit(client, amina, photo(1), client_ref="a-1").json()
    assert again["duplicate"] is True
    assert again["event"]["id"] == first["event"]["id"]
    assert len(client.get("/ledger").json()) == 1


def test_same_photo_new_reference_goes_to_review(client, amina, juma, live_model):
    live_model(GOOD)
    submit(client, amina, photo(1), client_ref="a-1")
    r = submit(client, juma, photo(1), client_ref="j-1", plot_id="2").json()
    assert r["event"]["status"] == "needs_human"
    assert any("same photograph" in x for x in r["event"]["review_reasons"])


def test_one_paid_submission_per_plot_per_window(client, amina, juma, live_model):
    live_model(GOOD)
    assert submit(client, amina, photo(1), client_ref="a-1").json()["event"]["status"] == "verified"
    r = submit(client, juma, photo(2), client_ref="j-1").json()
    assert r["event"]["status"] == "rejected"
    assert r["payment"] is None
    assert "already paid" in r["event"]["review_reasons"][0]


def test_far_from_plot_escalates_and_reviewer_approves(client, amina, lead, live_model):
    live_model(GOOD)
    r = submit(client, amina, photo(3), client_ref="a-3", lat="-4.0500", lon="39.6640").json()
    assert r["event"]["status"] == "needs_human"
    assert r["payment"] is None
    assert any("from the registered plot" in x for x in r["event"]["review_reasons"])
    eid = r["event"]["id"]

    # Monitors cannot see the queue or decide.
    assert client.get("/review/queue", headers=amina).status_code == 403
    queue = client.get("/review/queue", headers=lead).json()
    assert [q["id"] for q in queue] == [eid]
    assert client.get(f"/monitoring/events/{eid}/photo", headers=lead).status_code == 200

    assert client.post(f"/review/{eid}", json={"decision": "approve", "note": ""}, headers=lead).status_code == 400
    done = client.post(
        f"/review/{eid}",
        json={"decision": "approve", "note": "Plot marker visible; GPS drift under canopy."},
        headers=lead,
    ).json()
    assert done["event"]["status"] == "verified"
    assert done["payment"]["status"] == "success"
    entry = client.get("/ledger").json()[0]
    assert entry["reviewed_by_ref"] == "BP-M-0003"
    # A decided submission cannot be decided again.
    again = client.post(f"/review/{eid}", json={"decision": "reject", "note": "changed mind"}, headers=lead)
    assert again.status_code == 409


def test_species_dispute_escalates_without_overwriting_declaration(client, amina, live_model):
    live_model({**GOOD, "species_consistent": "no", "species_if_different": "Ceriops tagal"})
    r = submit(client, amina, photo(4), client_ref="a-4").json()
    assert r["event"]["status"] == "needs_human"
    assert r["event"]["detected_species"] == "Ceriops tagal"
    assert r["event"]["reported_species"] == PLOT["species"]


def test_fabricated_species_is_coerced_to_unclear(client, amina, live_model):
    live_model({**GOOD, "species_consistent": "no", "species_if_different": "Rhizophora apiculata"})
    r = submit(client, amina, photo(5), client_ref="a-5").json()
    assert r["event"]["detected_species"] == "unclear"
    assert r["event"]["status"] == "needs_human"


def test_illegible_escalates(client, amina, live_model):
    live_model({**GOOD, "legible": False})
    reasons = submit(client, amina, photo(6), client_ref="a-6").json()["event"]["review_reasons"]
    assert any("not legible" in x for x in reasons)


def test_model_failure_abstains_instead_of_crashing(client, amina, live_model):
    live_model(GOOD, status=500)
    r = submit(client, amina, photo(7), client_ref="a-7")
    assert r.status_code == 200
    assert r.json()["event"]["status"] == "needs_human"
    assert r.json()["event"]["verification_source"].startswith("error:")


def test_fenced_json_reply_is_parsed(client, amina, live_model):
    import json
    live_model("Here you go:\n```json\n" + json.dumps(GOOD) + "\n```")
    assert submit(client, amina, photo(8), client_ref="a-8").json()["event"]["status"] == "verified"


def test_no_photo_never_pays(client, amina):
    r = submit(client, amina, None, client_ref="a-9").json()
    assert r["event"]["status"] == "needs_human"
    assert r["payment"] is None


def test_no_gps_escalates(client, amina, live_model):
    live_model(GOOD)
    r = submit(client, amina, photo(10), client_ref="a-10", lat=None, lon=None).json()
    assert r["event"]["status"] == "needs_human"


def test_non_image_is_refused(client, amina):
    r = client.post(
        "/monitoring/submit-photo",
        data={"plot_id": "1"},
        files={"image": ("x.jpg", b"not an image at all", "image/jpeg")},
        headers=amina,
    )
    assert r.status_code == 400


def test_monitor_cannot_submit_as_someone_else(client, amina):
    r = submit(client, amina, photo(11), client_ref="x", monitor_id="2")
    assert r.status_code == 403


def test_monitor_sees_only_own_events(client, amina, juma, live_model):
    live_model(GOOD)
    submit(client, amina, photo(12), client_ref="a-12")
    assert client.get("/monitoring/events", headers=juma).json() == []
    assert len(client.get("/monitoring/events", headers=amina).json()) == 1
    assert client.get("/monitoring/events/1/photo", headers=juma).status_code == 404


def test_ledger_tampering_is_detected(client, amina, live_model):
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import LedgerEntry

    live_model(GOOD)
    submit(client, amina, photo(13), client_ref="a-13")
    submit(client, amina, photo(14), client_ref="a-14", plot_id="2", lat="-4.0141", lon="39.6711")
    assert client.get("/ledger/verify").json() == {"ok": True, "entries": 2, "head": client.get("/ledger").json()[-1]["entry_hash"]}

    with Session(engine) as s:
        first = s.exec(select(LedgerEntry).order_by(LedgerEntry.id)).first()
        first.amount_paid = 1500.0
        s.add(first)
        s.commit()
    v = client.get("/ledger/verify").json()
    assert v["ok"] is False and v["first_bad_id"] == 1 and "edited" in v["problem"]


def test_mock_mode_report_says_it_is_demonstration(client, amina, lead):
    for i in range(6):
        submit(client, amina, photo(100 + i), client_ref=f"m-{i}", plot_id=str(1 + i % 3))
    client.post("/satellite/refresh/1", headers=amina)
    report = client.get("/mrv/report/1").json()
    assert report["generated_by"] == "template"
    assert "submissions" in report["facts"]
    if "mock" in report["facts"]["verified_by_source"]:
        assert "DEMONSTRATION DATA" in report["narrative"]
