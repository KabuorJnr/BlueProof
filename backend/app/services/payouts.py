"""Release and settle payments. The only code that moves money.

Three callers (automatic verification, human approval, admin retry) share this
path so the ordering is always the same: a Payment row is committed first,
under a unique constraint on the event, then the rail is called, then the
ledger is written only once the money has actually moved.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..config import settings
from ..models import MonitoringEvent, Payment, PaymentStatus, User, VerificationStatus
from . import ledger, mpesa


async def release(session: Session, event: MonitoringEvent, monitor: User) -> Payment:
    if event.status != VerificationStatus.verified:
        raise ValueError("Only a verified event can be paid")

    payment = session.exec(
        select(Payment).where(Payment.monitoring_event_id == event.id)
    ).first()
    if payment is not None:
        return payment

    payment = Payment(
        monitoring_event_id=event.id,
        user_id=monitor.id,
        phone=monitor.phone,
        amount=settings.payout_per_verified_event,
    )
    session.add(payment)
    try:
        session.commit()
    except IntegrityError:
        # Another request released this event between our read and our write.
        session.rollback()
        return session.exec(
            select(Payment).where(Payment.monitoring_event_id == event.id)
        ).one()
    session.refresh(payment)
    return await _send(session, payment, event)


async def retry(session: Session, payment: Payment) -> Payment:
    if payment.status != PaymentStatus.failed:
        raise ValueError("Only a failed payment can be retried")
    event = session.get(MonitoringEvent, payment.monitoring_event_id)
    return await _send(session, payment, event)


async def _send(session: Session, payment: Payment, event: MonitoringEvent) -> Payment:
    payment.attempts += 1
    try:
        result = await mpesa.pay(payment.phone, payment.amount, reference=f"BP{event.id}")
    except Exception as exc:  # the rail being down must not lose the payment row
        result = {"status": "failed", "mpesa_ref": payment.mpesa_ref, "reason": f"{type(exc).__name__}: {exc}"}

    payment.mpesa_ref = result.get("mpesa_ref")
    payment.failure_reason = result.get("reason")
    session.add(payment)
    session.commit()

    if result["status"] == "success":
        settle(session, payment, True, result.get("receipt"), None)
    elif result["status"] == "failed":
        payment.status = PaymentStatus.failed
        session.add(payment)
        session.commit()
    else:
        payment.status = PaymentStatus.pending
        session.add(payment)
        session.commit()
    session.refresh(payment)
    return payment


def settle(
    session: Session, payment: Payment, success: bool, receipt: str | None, reason: str | None
) -> Payment:
    """Apply a final outcome. Idempotent: a replayed callback changes nothing."""
    if payment.status == PaymentStatus.success:
        return payment
    if success:
        payment.status = PaymentStatus.success
        payment.mpesa_receipt = receipt
        payment.failure_reason = None
        payment.settled_at = datetime.now(timezone.utc)
        session.add(payment)
        session.commit()
        event = session.get(MonitoringEvent, payment.monitoring_event_id)
        if event is not None:
            ledger.record_entry(session, event, payment.amount, mpesa_receipt=receipt)
    else:
        payment.status = PaymentStatus.failed
        payment.failure_reason = reason
        session.add(payment)
        session.commit()
    return payment
