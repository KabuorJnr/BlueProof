"""Payments, the M-Pesa B2C result callbacks, and admin retry."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, or_, select

from ..config import settings
from ..db import get_session
from ..models import Payment, PaymentStatus, User
from ..services import auth, mpesa, payouts

router = APIRouter(tags=["payments"])


@router.get("/payments")
def list_payments(
    user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[dict]:
    """Staff see every payment; a monitor sees their own."""
    q = select(Payment).order_by(Payment.created_at.desc())
    if not auth.is_staff(user):
        q = q.where(Payment.user_id == user.id)
    staff = auth.is_staff(user)
    return [p.model_dump(exclude=None if staff else {"phone"}) for p in session.exec(q).all()]


@router.post("/payments/{payment_id}/retry")
async def retry_payment(
    payment_id: int,
    _: User = Depends(auth.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    """Resend a failed payout.

    Before retrying a payment that failed on a queue TIMEOUT, check the M-Pesa
    organisation portal: a timeout does not always mean the money did not move.
    """
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "No such payment")
    try:
        payment = await payouts.retry(session, payment)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return payment.model_dump()


def _check_token(request: Request) -> None:
    expected = settings.mpesa_callback_token
    given = request.query_params.get("token", "")
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(403, "Bad callback token")


def _find(session: Session, parsed: dict) -> Payment | None:
    refs = [r for r in (parsed.get("ref"), parsed.get("conversation_id")) if r]
    if not refs:
        return None
    return session.exec(select(Payment).where(or_(*[Payment.mpesa_ref == r for r in refs]))).first()


@router.post("/mpesa/b2c/result", include_in_schema=False)
async def b2c_result(request: Request, session: Session = Depends(get_session)) -> dict:
    _check_token(request)
    parsed = mpesa.parse_result(await request.json())
    payment = _find(session, parsed)
    if payment is None:
        return {"ResultCode": 0, "ResultDesc": "Accepted, unmatched"}
    payouts.settle(session, payment, parsed["success"], parsed["receipt"], parsed["reason"])
    # Daraja expects an acknowledgement in this shape.
    return {"ResultCode": 0, "ResultDesc": "Accepted"}


@router.post("/mpesa/b2c/timeout", include_in_schema=False)
async def b2c_timeout(request: Request, session: Session = Depends(get_session)) -> dict:
    _check_token(request)
    parsed = mpesa.parse_result(await request.json())
    payment = _find(session, parsed)
    if payment is not None and payment.status == PaymentStatus.pending:
        payouts.settle(session, payment, False, None, "Queue timeout at Safaricom. Check the portal before retrying.")
    return {"ResultCode": 0, "ResultDesc": "Accepted"}
