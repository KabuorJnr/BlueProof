"""Auth, enrolment, privacy access, M-Pesa B2C and Sentinel-2 parsing."""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from app.config import settings
from app.services import http, sentinel
from conftest import GOOD, login, photo, submit

# ---- auth -------------------------------------------------------------------


def test_wrong_pin_then_lockout(client):
    for _ in range(settings.max_login_attempts):
        assert client.post("/auth/login", json={"phone": "254712000001", "pin": "0000"}).status_code == 401
    # Locked now, even with the right PIN.
    assert client.post("/auth/login", json={"phone": "254712000001", "pin": "1111"}).status_code == 423


def test_unknown_phone_and_wrong_pin_look_the_same(client):
    a = client.post("/auth/login", json={"phone": "254700000000", "pin": "1111"})
    b = client.post("/auth/login", json={"phone": "254712000001", "pin": "0000"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_forged_token_is_refused(client, amina):
    token = amina["Authorization"].split()[1]
    body, sig = token.split(".")
    forged = {"Authorization": f"Bearer {body}x.{sig}"}
    assert client.get("/auth/me", headers=forged).status_code == 401


# ---- enrolment and activation ------------------------------------------------


def enrol(client, phone="254799000001", headers=None, **kw):
    body = {"name": "New Monitor", "phone": phone, "pin": "4321", "consent_given": True, **kw}
    return client.post("/privacy/enrol", json=body, headers=headers or {})


def test_self_enrolled_monitor_cannot_be_paid_until_activated(client, lead, live_model):
    live_model(GOOD)
    r = enrol(client).json()
    assert r["active"] is False
    new = {"Authorization": f"Bearer {r['token']}"}
    first = submit(client, new, photo(21), client_ref="n-1").json()
    assert first["event"]["status"] == "needs_human"
    assert any("not yet activated" in x for x in first["event"]["review_reasons"])

    # The lead cannot approve payment to an inactive account...
    eid = first["event"]["id"]
    blocked = client.post(f"/review/{eid}", json={"decision": "approve", "note": "known member"}, headers=lead)
    assert blocked.status_code == 409
    # ...activates them in person, then approves.
    assert client.post(f"/users/{r['user_id']}/activate", json={"active": True}, headers=lead).json()["active"]
    ok = client.post(f"/review/{eid}", json={"decision": "approve", "note": "known member"}, headers=lead).json()
    assert ok["payment"]["status"] == "success"


def test_enrolment_by_staff_is_active_immediately(client, lead):
    assert enrol(client, headers=lead).json()["active"] is True


def test_enrolment_needs_consent_and_a_valid_pin(client):
    assert enrol(client, consent_given=False).status_code == 400
    assert enrol(client, pin="12").status_code == 422


def test_privacy_export_and_delete_are_self_only(client, amina, juma, admin):
    assert client.get("/privacy/export/1", headers=juma).status_code == 403
    assert client.get("/privacy/export/1", headers=amina).status_code == 200
    assert client.post("/privacy/delete", json={"user_id": 1, "confirm_phrase": "FUTA"}, headers=juma).status_code == 403
    assert client.get("/privacy/export/1").status_code == 401


def test_deletion_purges_photos_but_keeps_hash(client, amina, live_model):
    live_model(GOOD)
    sub = submit(client, amina, photo(22), client_ref="d-1").json()
    r = client.post("/privacy/delete", json={"user_id": 1, "confirm_phrase": "FUTA"}, headers=amina).json()
    assert r["deleted"]["photographs"] == 1
    entry = client.get("/ledger").json()[0]
    assert entry["photo_sha256"] == sub["event"]["photo_sha256"]
    assert client.get("/ledger/verify").json()["ok"] is True


def test_payments_list_hides_phone_from_monitors(client, amina, admin, live_model):
    live_model(GOOD)
    submit(client, amina, photo(23), client_ref="p-1")
    assert "phone" not in client.get("/payments", headers=amina).json()[0]
    assert client.get("/payments", headers=admin).json()[0]["phone"] == "254712000001"
    assert client.get("/payments").status_code == 401


# ---- M-Pesa B2C ----------------------------------------------------------------


@pytest.fixture
def daraja(monkeypatch):
    monkeypatch.setattr(settings, "mpesa_mode", "sandbox")
    for k, v in {
        "mpesa_consumer_key": "ck", "mpesa_consumer_secret": "cs", "mpesa_shortcode": "600000",
        "mpesa_initiator_name": "testapi", "mpesa_security_credential": "cred",
        "public_base_url": "https://bp.test", "mpesa_callback_token": "cb-secret",
    }.items():
        monkeypatch.setattr(settings, k, v)
    calls: list[httpx.Request] = []
    llm = json.dumps(GOOD)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "oauth" in request.url.path:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": "3599"})
        if "b2c" in request.url.path:
            sent = json.loads(request.content)
            return httpx.Response(200, json={
                "ConversationID": "AG_20260923_x", "OriginatorConversationID": sent["OriginatorConversationID"],
                "ResponseCode": "0", "ResponseDescription": "Accept the service request successfully.",
            })
        return httpx.Response(200, json={"choices": [{"message": {"content": llm}}]})

    monkeypatch.setattr(settings, "llama_api_url", "https://llm.test/v1/chat/completions")
    http.transport = httpx.MockTransport(handler)
    return calls


def test_b2c_pays_the_monitor_and_ledger_waits_for_the_result(client, amina, daraja):
    r = submit(client, amina, photo(31), client_ref="b-1").json()
    assert r["payment"]["status"] == "pending"
    assert client.get("/ledger").json() == []

    b2c = [c for c in daraja if "b2c" in c.url.path][0]
    sent = json.loads(b2c.content)
    # Money goes TO the monitor: the business is PartyA, the phone is PartyB.
    assert sent["CommandID"] == "BusinessPayment"
    assert sent["PartyA"] == "600000" and sent["PartyB"] == "254712000001"
    assert sent["Amount"] == 150
    assert sent["ResultURL"] == "https://bp.test/mpesa/b2c/result?token=cb-secret"

    callback = {"Result": {
        "ResultType": 0, "ResultCode": 0, "ResultDesc": "The service request is processed successfully.",
        "OriginatorConversationID": sent["OriginatorConversationID"], "ConversationID": "AG_20260923_x",
        "TransactionID": "SIN4XYZ123",
    }}
    assert client.post("/mpesa/b2c/result?token=wrong", json=callback).status_code == 403
    assert client.post("/mpesa/b2c/result?token=cb-secret", json=callback).status_code == 200
    # Safaricom retries callbacks; a replay must not write a second line.
    client.post("/mpesa/b2c/result?token=cb-secret", json=callback)

    ledger = client.get("/ledger").json()
    assert len(ledger) == 1 and ledger[0]["mpesa_receipt"] == "SIN4XYZ123"


def test_b2c_failure_then_admin_retry(client, amina, admin, daraja):
    r = submit(client, amina, photo(32), client_ref="b-2").json()
    sent = json.loads([c for c in daraja if "b2c" in c.url.path][0].content)
    client.post("/mpesa/b2c/result?token=cb-secret", json={"Result": {
        "ResultCode": 2001, "ResultDesc": "The initiator information is invalid.",
        "OriginatorConversationID": sent["OriginatorConversationID"],
    }})
    pays = client.get("/payments", headers=admin).json()
    assert pays[0]["status"] == "failed" and "initiator" in pays[0]["failure_reason"]
    assert client.post(f"/payments/{pays[0]['id']}/retry", headers=amina).status_code == 403
    again = client.post(f"/payments/{pays[0]['id']}/retry", headers=admin).json()
    assert again["status"] == "pending" and again["attempts"] == 2
    assert r["event"]["status"] == "verified"


def test_production_refuses_unsafe_config(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.check()


# ---- Sentinel-2 ----------------------------------------------------------------


def stats_item(day: str, mean, samples=1000, nodata=100):
    return {
        "interval": {"from": f"{day}T00:00:00Z", "to": f"{day}T00:00:00Z"},
        "outputs": {"ndvi": {"bands": {"B0": {"stats": {
            "min": 0.1, "max": 0.9, "mean": mean, "stDev": 0.1,
            "sampleCount": samples, "noDataCount": nodata,
        }}}}},
    }


def test_parse_stats_screens_cloud_and_needs_sustained_drop():
    body = {"data": [
        stats_item("2026-06-01", 0.60),
        stats_item("2026-06-06", 0.50),                    # one low scene: no alert yet
        stats_item("2026-06-11", 0.49, nodata=900),         # 90% cloud: stored, not trusted
        stats_item("2026-06-16", 0.48),                     # second trusted low: alert
        stats_item("2026-06-21", "NaN", nodata=1000),       # fully cloudy: dropped
        stats_item("2026-06-26", 0.61, samples=0, nodata=0),  # no acquisition: dropped
    ]}
    rows = sentinel.parse_stats(body, baseline=0.62)
    assert [r["observed_on"] for r in rows] == [date(2026, 6, 1), date(2026, 6, 6), date(2026, 6, 11), date(2026, 6, 16)]
    assert [r["alert"] for r in rows] == [False, False, False, True]
    assert rows[2]["cloud_fraction"] == 0.9


def test_live_refresh_calls_statistical_api(client, amina, monkeypatch):
    monkeypatch.setattr(settings, "copernicus_client_id", "id")
    monkeypatch.setattr(settings, "copernicus_client_secret", "secret")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "token" in request.url.path:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 600})
        return httpx.Response(200, json={"data": [stats_item("2026-09-01", 0.58)], "status": "OK"})

    http.transport = httpx.MockTransport(handler)
    r = client.post("/satellite/refresh/1", headers=amina).json()
    assert r["mode"] == "sentinel-2" and r["observations"] == 1
    req = json.loads(seen[-1].content)
    assert req["input"]["data"][0]["type"] == "sentinel-2-l2a"
    assert "SCL" in req["aggregation"]["evalscript"]
    assert req["input"]["bounds"]["geometry"]["type"] == "Polygon"
