"""The public, pseudonymous stewardship ledger, its integrity check, and admin housekeeping."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import LedgerEntry, MonitoringEvent, User, VerificationStatus
from ..services import auth, ledger, photos

router = APIRouter(tags=["ledger"])


@router.get("/ledger", response_model=list[LedgerEntry])
def entries(site_id: int | None = None, session: Session = Depends(get_session)) -> list[LedgerEntry]:
    """Public. Carries pseudonyms, never names or phone numbers."""
    q = select(LedgerEntry).order_by(LedgerEntry.id)
    if site_id is not None:
        q = q.where(LedgerEntry.site_id == site_id)
    return session.exec(q).all()


@router.get("/ledger.csv", response_class=PlainTextResponse)
def entries_csv(session: Session = Depends(get_session)) -> str:
    rows = session.exec(select(LedgerEntry).order_by(LedgerEntry.id)).all()
    buf = io.StringIO()
    fields = list(LedgerEntry.model_fields)
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r.model_dump())
    return buf.getvalue()


@router.get("/ledger/verify")
def verify(session: Session = Depends(get_session)) -> dict:
    """Recompute the hash chain. Anyone holding an earlier export can compare heads."""
    return ledger.verify_chain(session)


@router.post("/admin/purge-photos")
def purge_photos(
    _: User = Depends(auth.require_admin), session: Session = Depends(get_session)
) -> dict:
    """Delete photographs older than PHOTO_RETENTION_DAYS on finished submissions.

    Submissions still awaiting review keep their photo, since a person has yet
    to look at it. The hash stays on the submission and in the ledger.
    """
    if not settings.photo_retention_days:
        raise HTTPException(400, "PHOTO_RETENTION_DAYS is not set; nothing is purged.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.photo_retention_days)
    events = session.exec(
        select(MonitoringEvent)
        .where(MonitoringEvent.photo_sha256.is_not(None))
        .where(MonitoringEvent.photo_purged == False)  # noqa: E712
        .where(MonitoringEvent.status != VerificationStatus.needs_human)
        .where(MonitoringEvent.created_at < cutoff)
    ).all()
    for e in events:
        photos.delete(e.photo_sha256)
        if e.marker_sha256:
            photos.delete(e.marker_sha256)
        e.photo_purged = True
        session.add(e)
    session.commit()
    return {"purged": len(events), "older_than_days": settings.photo_retention_days}
