"""Field monitoring: submit evidence, verify it, pay on proof, review the rest.

Design decision worth defending in the pitch: a monitor is paid for a VERIFIED
SUBMISSION, not for a surviving seedling. If pay depended on survival, the
incentive would be to hide deaths, and the data would rot. Paying for honest,
verifiable reporting keeps the record truthful, which is the only thing a buyer
is actually purchasing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import (
    MonitoringEvent,
    Payment,
    PaymentStatus,
    Plot,
    User,
    VerificationStatus,
)
from ..schemas import Verdict
from ..services import auth, gate, llama_vision, payouts, photos

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _event_out(event: MonitoringEvent) -> dict:
    out = event.model_dump()
    out["review_reasons"] = json.loads(event.review_reasons or "[]")
    return out


def _response(session: Session, event: MonitoringEvent, duplicate: bool = False) -> dict:
    payment = session.exec(
        select(Payment).where(Payment.monitoring_event_id == event.id)
    ).first()
    if event.status == VerificationStatus.needs_human:
        note = "Escalated for human review, no payment released."
    elif event.status == VerificationStatus.rejected:
        note = "Recorded, not paid."
    elif payment is not None and payment.status == PaymentStatus.success:
        note = "Verified and paid."
    elif payment is not None and payment.status == PaymentStatus.failed:
        note = "Verified. The payment failed and will be retried by an admin."
    else:
        note = "Verified. Payment is being processed."
    return {
        "event": _event_out(event),
        "payment": payment.model_dump(exclude={"phone"}) if payment else None,
        "note": note,
        "duplicate": duplicate,
    }


def _last_paid_at(session: Session, plot_id: int, exclude_event: int | None = None) -> datetime | None:
    rows = session.exec(
        select(MonitoringEvent)
        .where(MonitoringEvent.plot_id == plot_id)
        .where(MonitoringEvent.status == VerificationStatus.verified)
        .order_by(MonitoringEvent.verified_at.desc())
    ).all()
    for r in rows:
        if r.id != exclude_event and r.verified_at is not None:
            return r.verified_at
    return None


def _previous_verified_photo(session: Session, plot_id: int) -> tuple[MonitoringEvent, bytes] | None:
    """The most recent verified submission on this plot whose photo is still held."""
    rows = session.exec(
        select(MonitoringEvent)
        .where(MonitoringEvent.plot_id == plot_id)
        .where(MonitoringEvent.status == VerificationStatus.verified)
        .where(MonitoringEvent.photo_sha256.is_not(None))
        .where(MonitoringEvent.photo_purged == False)  # noqa: E712
        .order_by(MonitoringEvent.created_at.desc())
    ).all()
    for r in rows:
        data = photos.load(r.photo_sha256)
        if data is not None:
            return r, data
    return None


@router.post("/verify-photo", response_model=Verdict)
async def verify_photo(
    image: UploadFile = File(...),
    declared_species: str | None = Form(default=None),
    _: User = Depends(auth.require_staff),
) -> Verdict:
    """Run the verifier over a photograph without recording anything. Staff only."""
    photo = photos.inspect(await image.read())
    try:
        return await llama_vision.verify_plot(photo.data, declared_species, photo.mime)
    except llama_vision.VerifierError as exc:
        raise HTTPException(502, f"Verifier unavailable: {exc}") from exc


@router.post("/submit-photo")
async def submit_photo(
    plot_id: int = Form(...),
    image: UploadFile | None = File(default=None),
    marker: UploadFile | None = File(default=None),
    reported_species: str | None = Form(default=None),
    reported_survival: int | None = Form(default=None),
    lat: float | None = Form(default=None),
    lon: float | None = Form(default=None),
    client_ref: str | None = Form(default=None),
    monitor_id: int | None = Form(default=None),
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Submit a monitoring event with its photograph.

    `image` is the evidence shot (protocol shot 3, the close-up). `marker` is
    the plot marker shot (protocol shot 1); when sent, the model reads the code
    on it and the gate checks it against the plot.

    The monitor is whoever is signed in. Staff may submit on behalf of a
    monitor (a CFA lead uploading from a shared phone) by naming monitor_id.
    """
    if monitor_id is not None and monitor_id != user.id:
        if not auth.is_staff(user):
            raise HTTPException(403, "You can only submit as yourself.")
        monitor = session.get(User, monitor_id)
        if monitor is None:
            raise HTTPException(404, "Monitor not found")
    else:
        monitor = user

    # Idempotency: the offline queue retries until it hears back, and a retry
    # after a lost response must return the original outcome, not pay again.
    if client_ref:
        prior = session.exec(
            select(MonitoringEvent).where(MonitoringEvent.client_ref == client_ref)
        ).first()
        if prior is not None:
            if prior.monitor_id != monitor.id:
                raise HTTPException(409, "That submission reference belongs to someone else.")
            return _response(session, prior, duplicate=True)

    plot = session.get(Plot, plot_id)
    if plot is None:
        raise HTTPException(404, "Plot not found")

    photo = photos.inspect(await image.read()) if image is not None else None
    declared = (reported_species or plot.species).strip()

    exact_dup = near_dup = None
    if photo is not None:
        same = session.exec(
            select(MonitoringEvent).where(MonitoringEvent.photo_sha256 == photo.sha256)
        ).first()
        if same is not None:
            if same.monitor_id == monitor.id and same.plot_id == plot.id and not client_ref:
                # The same person resending the same bytes for the same plot
                # with no reference: an old client retrying. Same answer.
                return _response(session, same, duplicate=True)
            exact_dup = same.id
        else:
            for prior in session.exec(
                select(MonitoringEvent).where(MonitoringEvent.photo_dhash.is_not(None))
            ).all():
                if photos.hamming(prior.photo_dhash, photo.dhash) <= settings.near_duplicate_distance:
                    near_dup = prior.id
                    break

    if photo is None:
        verdict = Verdict(
            source="none", legible=False, species_consistent="unclear", detected_species="unclear",
            seedlings_visible=0, health="unclear", evidence_of_cutting=False, pest_damage=False,
            confidence=0.0, reasoning="No photograph was submitted.",
        )
    else:
        try:
            verdict = await llama_vision.verify_plot(photo.data, declared, photo.mime)
        except llama_vision.VerifierError as exc:
            # Abstain, never crash: the submission is kept and a person decides.
            verdict = Verdict(
                source=f"error:{llama_vision.source_label()}", legible=False,
                species_consistent="unclear", detected_species="unclear", seedlings_visible=0,
                health="unclear", evidence_of_cutting=False, pest_damage=False, confidence=0.0,
                reasoning=f"Verifier failed: {exc}",
            )

    marker_photo = photos.inspect(await marker.read()) if marker is not None else None
    marker_read: dict | None = None
    if marker_photo is not None:
        try:
            marker_read = await llama_vision.read_marker(marker_photo.data, plot.code, marker_photo.mime)
        except llama_vision.VerifierError as exc:
            # Unreadable is not a reason to block; it is recorded and GPS stands.
            marker_read = {"legible": False, "code": None, "source": f"error: {exc}"}

    comparison: dict | None = None
    previous = _previous_verified_photo(session, plot.id) if photo is not None and exact_dup is None else None
    if previous is not None:
        prev_event, prev_bytes = previous
        try:
            stitched = photos.side_by_side(prev_bytes, photo.data, f"{prev_event.created_at:%Y-%m-%d}")
            comparison = await llama_vision.compare_visits(stitched)
        except (llama_vision.VerifierError, OSError) as exc:
            comparison = {"same_location": "unclear", "change": "unclear", "note": f"Comparison failed: {exc}"}
        comparison["previous_event_id"] = prev_event.id

    distance = None
    if lat is not None and lon is not None:
        distance = round(photos.distance_m(lat, lon, plot.lat, plot.lon), 1)

    now = datetime.now(timezone.utc)
    result = gate.decide(gate.GateInput(
        verdict=verdict,
        has_photo=photo is not None,
        distance_m=distance,
        exact_duplicate_of=exact_dup,
        near_duplicate_of=near_dup,
        last_paid_at=_last_paid_at(session, plot.id),
        now=now,
        monitor_active=monitor.active,
        marker_sent=marker_photo is not None,
        marker_code_read=(marker_read or {}).get("code"),
        plot_code=plot.code,
        same_location=(comparison or {}).get("same_location"),
        previous_event_id=(comparison or {}).get("previous_event_id"),
    ))

    event = MonitoringEvent(
        plot_id=plot.id,
        monitor_id=monitor.id,
        client_ref=client_ref,
        photo_ref=photos.store(photo) if photo else None,
        photo_sha256=photo.sha256 if photo else None,
        photo_dhash=photo.dhash if photo else None,
        marker_sha256=photos.store(marker_photo) if marker_photo else None,
        marker_code_read=(marker_read or {}).get("code"),
        marker_matches=(
            None if not (marker_read and marker_read.get("code"))
            else not gate.marker_mismatch(marker_read["code"], plot.code)
        ),
        previous_event_id=(comparison or {}).get("previous_event_id"),
        same_location=(comparison or {}).get("same_location"),
        change_vs_previous=(comparison or {}).get("change"),
        change_note=(comparison or {}).get("note"),
        reported_species=declared,
        reported_survival=reported_survival,
        lat=lat,
        lon=lon,
        distance_from_plot_m=distance,
        status=result.status,
        verification_source=verdict.source,
        legible=verdict.legible,
        species_consistent=verdict.species_consistent,
        detected_species=verdict.detected_species,
        seedlings_visible=verdict.seedlings_visible,
        health=verdict.health,
        evidence_of_cutting=verdict.evidence_of_cutting,
        pest_damage=verdict.pest_damage,
        confidence=verdict.confidence,
        self_reported_confidence=verdict.self_reported_confidence,
        verifier_samples=verdict.samples,
        reasoning=verdict.reasoning,
        review_reasons=json.dumps(result.reasons),
        verified_at=now if result.payable else None,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    if result.payable:
        await payouts.release(session, event, monitor)
    return _response(session, event)


@router.get("/events")
def list_events(
    status: VerificationStatus | None = None,
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Staff see every submission; a monitor sees their own."""
    q = select(MonitoringEvent).order_by(MonitoringEvent.created_at.desc())
    if not auth.is_staff(user):
        q = q.where(MonitoringEvent.monitor_id == user.id)
    if status is not None:
        q = q.where(MonitoringEvent.status == status)
    return [_event_out(e) for e in session.exec(q).all()]


@router.get("/events/{event_id}")
def get_event(
    event_id: int, user: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> dict:
    event = session.get(MonitoringEvent, event_id)
    if event is None or (event.monitor_id != user.id and not auth.is_staff(user)):
        raise HTTPException(404, "No such submission")
    return _response(session, event)


@router.get("/events/{event_id}/photo")
def event_photo(
    event_id: int,
    kind: str = "evidence",
    user: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> Response:
    """The evidence photograph, or with kind=marker the plot marker shot."""
    event = session.get(MonitoringEvent, event_id)
    if event is None or (event.monitor_id != user.id and not auth.is_staff(user)):
        raise HTTPException(404, "No such submission")
    sha = event.marker_sha256 if kind == "marker" else event.photo_sha256
    data = photos.load(sha) if sha else None
    if data is None:
        raise HTTPException(410 if event.photo_purged else 404, "Photograph not held")
    return Response(content=data, media_type=photos.mime_of(data), headers={"Cache-Control": "private, max-age=3600"})


@router.get("/alerts")
def list_alerts(
    _: User = Depends(auth.current_user), session: Session = Depends(get_session)
) -> list[dict]:
    """Field reported threats: cutting and pest damage, newest first."""
    events = session.exec(
        select(MonitoringEvent)
        .where((MonitoringEvent.evidence_of_cutting == True) | (MonitoringEvent.pest_damage == True))  # noqa: E712
        .order_by(MonitoringEvent.created_at.desc())
    ).all()
    return [
        {
            "event_id": e.id, "plot_id": e.plot_id, "created_at": e.created_at,
            "cutting": e.evidence_of_cutting, "pests": e.pest_damage,
            "status": e.status, "lat": e.lat, "lon": e.lon,
        }
        for e in events
    ]


# ---- Human review --------------------------------------------------------

review = APIRouter(prefix="/review", tags=["review"])


@review.get("/queue")
def queue(_: User = Depends(auth.require_staff), session: Session = Depends(get_session)) -> list[dict]:
    """Escalated submissions, oldest first, with what the reviewer needs to decide."""
    events = session.exec(
        select(MonitoringEvent)
        .where(MonitoringEvent.status == VerificationStatus.needs_human)
        .order_by(MonitoringEvent.created_at)
    ).all()
    out = []
    for e in events:
        plot = session.get(Plot, e.plot_id)
        monitor = session.get(User, e.monitor_id)
        out.append({
            **_event_out(e),
            "plot_code": plot.code if plot else None,
            "plot_species": plot.species if plot else None,
            "monitor_ref": monitor.public_ref if monitor else "deleted",
            "monitor_active": bool(monitor and monitor.active),
            "has_photo": bool(e.photo_sha256 and not e.photo_purged),
            "has_marker": bool(e.marker_sha256 and not e.photo_purged),
        })
    return out


class ReviewDecision(BaseModel):
    decision: str                 # approve | reject
    note: str
    health: str | None = None     # a reviewer may correct the condition
    seedlings_visible: int | None = None


@review.post("/{event_id}")
async def decide(
    event_id: int,
    body: ReviewDecision,
    reviewer: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> dict:
    event = session.get(MonitoringEvent, event_id)
    if event is None:
        raise HTTPException(404, "No such submission")
    if event.status != VerificationStatus.needs_human:
        raise HTTPException(409, f"Submission is {event.status.value}, not awaiting review.")
    if event.monitor_id == reviewer.id:
        raise HTTPException(403, "Nobody reviews their own submission.")
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve or reject")
    if len(body.note.strip()) < 3:
        raise HTTPException(400, "Say why. A decision with no reason cannot be audited.")

    now = datetime.now(timezone.utc)
    monitor = session.get(User, event.monitor_id)

    if body.decision == "approve":
        if monitor is None:
            raise HTTPException(409, "The monitor's account was deleted; this cannot be paid.")
        blockers = gate.review_blockers(_last_paid_at(session, event.plot_id), now, monitor.active)
        if blockers:
            raise HTTPException(409, " ".join(blockers))
        if body.health is not None:
            if body.health not in {"healthy", "stressed", "dead"}:
                raise HTTPException(400, "health must be healthy, stressed or dead")
            event.health = body.health
        elif event.health == "unclear":
            raise HTTPException(400, "Condition is unclear; state healthy, stressed or dead to approve.")
        if body.seedlings_visible is not None:
            event.seedlings_visible = max(0, body.seedlings_visible)
        event.status = VerificationStatus.verified
        event.verified_at = now
    else:
        event.status = VerificationStatus.rejected

    event.reviewed_by = reviewer.id
    event.reviewed_at = now
    event.review_note = body.note.strip()
    session.add(event)
    session.commit()
    session.refresh(event)

    if event.status == VerificationStatus.verified:
        await payouts.release(session, event, monitor)
    return _response(session, event)
