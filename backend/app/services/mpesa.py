"""Send a payout to a community monitor over M-Pesa B2C.

B2C (business to customer) is the Daraja API that moves money from the
project's shortcode to a person's phone. The earlier version of this module
used STK Push, which does the opposite: it asks the person to pay the
business. That would have prompted a monitor for KSh 150 every time their work
was verified.

B2C is asynchronous. The request returns "accepted"; the money moves later and
Safaricom posts the outcome to our ResultURL (api/payments.py). Until then the
payment is pending and no ledger line is written.

What you need from Safaricom for this to run for real, which no code can
supply: a B2C-enabled shortcode on a registered organisation, an initiator
user on that shortcode, and the initiator's security credential generated on
the Daraja portal. Sandbox gives you test versions of all three.
"""
from __future__ import annotations

import base64
import secrets
import time

from ..config import settings
from . import http

BASE = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}

_token: dict = {"value": None, "expires": 0.0}


def is_live() -> bool:
    return settings.mpesa_mode in BASE


def _base() -> str:
    return BASE[settings.mpesa_mode]


async def _access_token() -> str:
    if _token["value"] and _token["expires"] > time.time() + 60:
        return _token["value"]
    auth = base64.b64encode(
        f"{settings.mpesa_consumer_key}:{settings.mpesa_consumer_secret}".encode()
    ).decode()
    async with http.client(30) as client:
        resp = await client.get(
            f"{_base()}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {auth}"},
        )
        resp.raise_for_status()
        data = resp.json()
    _token["value"] = data["access_token"]
    _token["expires"] = time.time() + int(data.get("expires_in", 3599))
    return _token["value"]


def callback_url(kind: str) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/mpesa/b2c/{kind}?token={settings.mpesa_callback_token}"


async def pay(phone: str, amount: float, reference: str) -> dict:
    """Start a payout. Returns {status, mpesa_ref, receipt?, reason?}.

    status is "success" (mock only), "pending" (accepted by Daraja, awaiting
    the result callback) or "failed" (refused at submission).
    """
    originator = f"BP-{reference}-{secrets.token_hex(6)}"
    if not is_live():
        return {"status": "success", "mpesa_ref": originator, "receipt": f"MOCK{secrets.token_hex(4).upper()}"}

    token = await _access_token()
    payload = {
        "OriginatorConversationID": originator,
        "InitiatorName": settings.mpesa_initiator_name,
        "SecurityCredential": settings.mpesa_security_credential,
        "CommandID": "BusinessPayment",
        "Amount": int(round(amount)),
        "PartyA": settings.mpesa_shortcode,
        "PartyB": phone,
        "Remarks": "BlueProof stewardship payment",
        "QueueTimeOutURL": callback_url("timeout"),
        "ResultURL": callback_url("result"),
        # Daraja's spelling.
        "Occassion": reference,
    }
    async with http.client(30) as client:
        resp = await client.post(
            f"{_base()}/mpesa/b2c/v3/paymentrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code == 200 and str(data.get("ResponseCode")) == "0":
        return {"status": "pending", "mpesa_ref": data.get("OriginatorConversationID") or originator}
    reason = data.get("errorMessage") or data.get("ResponseDescription") or f"HTTP {resp.status_code}"
    return {"status": "failed", "mpesa_ref": originator, "reason": str(reason)}


def parse_result(body: dict) -> dict:
    """Read a B2C result callback into {ref, success, receipt, reason}."""
    result = body.get("Result") or {}
    return {
        "ref": result.get("OriginatorConversationID"),
        "conversation_id": result.get("ConversationID"),
        "success": str(result.get("ResultCode")) == "0",
        "receipt": result.get("TransactionID"),
        "reason": result.get("ResultDesc"),
    }
