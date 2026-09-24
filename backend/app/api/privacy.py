"""Enrolment, consent, and the rights a person has over their own record.

Three things live here, and they are one subject rather than three.

**Enrolment** is the only door through which a name and a phone number enter
this system. It is therefore the only place consent can honestly be taken, and
the only place the question of age can be asked.

**Export** answers "what do you hold about me". The Data Protection Act 2019
gives a data subject that right at section 26, and a right that requires an
email to a founder who may be in a lecture is a right on paper. It is an
endpoint.

**Deletion** answers "stop holding it". This is the hard one, because the
stewardship ledger is the product, and a record that can be quietly removed by
whoever it inconveniences is not evidence of anything. Those two obligations
genuinely collide, and the resolution is not to pick a side:

  * Everything that identifies a person is erased. Name, phone number, guardian
    details, consent record: gone, not blanked out and recoverable.
  * The environmental record stays, permanently severed from them. It was
    already pseudonymous, and after erasure the pseudonym points at nobody.
  * The payment rows keep the phone number, because the Central Bank of Kenya
    requires payment records to be retained for seven years and a regulator's
    retention obligation is a lawful basis that survives a deletion request.
    The person is told this, in the response, in terms rather than by reference
    to a statute number.

What that adds up to is that a monitor can always disappear from the system,
and can never be made to disappear from the record of work they did. Both of
those seem right.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..db import get_session
from ..models import LedgerEntry, MonitoringEvent, Payment, Role, User
from ..services import auth, photos

router = APIRouter(prefix="/privacy", tags=["privacy"])

# Bumped whenever the wording of what people agree to changes. Storing the
# version, not just a boolean, is what makes it possible to answer "what
# exactly did this person agree to" a year later, which is the only form of
# the question that matters in a dispute.
CONSENT_VERSION = "2026-09-18"


class Enrolment(BaseModel):
    """Everything needed to enrol a monitor, and nothing else.

    There is no date of birth field and that is deliberate. The system needs to
    know whether a guardian must consent. It never needs to know how old
    somebody is, and a date of birth is both more sensitive and more permanent
    than the answer to the only question being asked.
    """
    name: str
    phone: str
    # Chosen by the monitor, 4 to 8 digits. Only its hash is stored.
    pin: str
    cfa: str | None = None

    consent_given: bool
    is_minor: bool = False
    guardian_name: str | None = None
    guardian_phone: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not (v.startswith("254") and len(v) == 12 and v.isdigit()):
            raise ValueError("Phone must be in the format 2547XXXXXXXX")
        return v

    @field_validator("pin")
    @classmethod
    def _pin(cls, v: str) -> str:
        v = v.strip()
        if not auth.valid_pin(v):
            raise ValueError("PIN must be 4 to 8 digits")
        return v


class DeletionRequest(BaseModel):
    user_id: int
    # Typed by the person, and checked, so that a deletion cannot be triggered
    # by a stray tap or by somebody else holding the handset.
    confirm_phrase: str


def _self_or(user: User, user_id: int, admin_only: bool = False) -> None:
    if user.id == user_id:
        return
    if user.role == Role.admin or (not admin_only and auth.is_staff(user)):
        return
    raise HTTPException(403, "You can only do this for your own record.")


@router.post("/enrol")
def enrol(
    body: Enrolment,
    session: Session = Depends(get_session),
    staff: User | None = Depends(auth.optional_user),
) -> dict:
    """Enrol a monitor, with consent recorded rather than assumed.

    Anyone may enrol, but a self-enrolled account cannot be paid until a CFA
    lead activates it: payouts go to real members of a real group. Enrolment
    performed by a signed-in CFA lead, in person, is active at once.
    """
    if not body.consent_given:
        # Not an error to be worked around. Without consent there is no lawful
        # basis to hold the name and number, so there is nothing to create.
        raise HTTPException(
            400,
            "Cannot enrol without consent. Nothing has been stored.",
        )

    # The Youth Climate Action Fund targets ages 15 to 24, so under 18s are an
    # expected part of this cohort rather than an edge case. A minor's data is
    # held only where an adult with responsibility for them has agreed to it.
    if body.is_minor and not (body.guardian_name and body.guardian_phone):
        raise HTTPException(
            400,
            "A monitor under 18 needs a parent or guardian's name and phone "
            "number before anything can be stored.",
        )

    existing = session.exec(select(User).where(User.phone == body.phone)).first()
    if existing is not None:
        raise HTTPException(409, "That phone number is already enrolled.")

    now = datetime.now(timezone.utc)
    user = User(
        name=body.name.strip(),
        phone=body.phone,
        role=Role.monitor,
        cfa=body.cfa,
        consent_version=CONSENT_VERSION,
        consented_at=now,
        is_minor=body.is_minor,
        guardian_name=body.guardian_name,
        guardian_phone=body.guardian_phone,
        pin_hash=auth.hash_pin(body.pin),
        active=auth.is_staff(staff),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # The pseudonym is derived from the row id, so it needs the insert to have
    # happened first.
    user.public_ref = f"BP-M-{user.id:04d}"
    session.add(user)
    session.commit()
    session.refresh(user)

    return {
        "user_id": user.id,
        "public_ref": user.public_ref,
        "consent_version": user.consent_version,
        "active": user.active,
        "token": auth.issue_token(user),
        "message": (
            "Enrolled. Your name and phone number are held only to pay you and "
            "to answer questions about your work. The public record uses "
            f"{user.public_ref}, not your name."
            + ("" if user.active else " A CFA lead must confirm you before you can be paid.")
        ),
    }


@router.get("/export/{user_id}")
def export(
    user_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(auth.current_user),
) -> dict:
    """Everything held about one person, in one response.

    Including the things that are awkward to show: which submissions were
    escalated rather than paid, and what the verifier said about them. A
    subject access right that returns only the flattering half is not one.
    """
    _self_or(caller, user_id)
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "No such person")

    events = session.exec(
        select(MonitoringEvent).where(MonitoringEvent.monitor_id == user_id)
    ).all()
    payments = session.exec(select(Payment).where(Payment.user_id == user_id)).all()
    entries = session.exec(
        select(LedgerEntry).where(LedgerEntry.monitor_ref == user.public_ref)
    ).all()

    return {
        "about_you": {
            "name": user.name,
            "phone": user.phone,
            "cfa": user.cfa,
            "public_ref": user.public_ref,
            "role": user.role,
            "enrolled_at": user.created_at,
            "consent_version": user.consent_version,
            "consented_at": user.consented_at,
            "guardian_name": user.guardian_name,
            "guardian_phone": user.guardian_phone,
        },
        "your_submissions": [e.model_dump() for e in events],
        "your_payments": [p.model_dump() for p in payments],
        "public_record_entries": [e.model_dump() for e in entries],
        "what_we_do_not_hold": [
            "Your date of birth or your age.",
            "Your national ID number.",
            "Your location when you are not submitting a plot.",
            "Anything about you from any other service.",
        ],
    }


@router.post("/delete")
def delete(
    body: DeletionRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(auth.current_user),
) -> dict:
    """Erase the person. Keep the environmental record, severed from them."""
    _self_or(caller, body.user_id, admin_only=True)
    user = session.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "No such person")

    if body.confirm_phrase.strip().upper() != "FUTA":
        raise HTTPException(
            400,
            "To confirm deletion, type FUTA. Nothing has been changed.",
        )

    ref = user.public_ref or f"BP-M-{user.id:04d}"
    payments = session.exec(select(Payment).where(Payment.user_id == user.id)).all()
    entries = session.exec(select(LedgerEntry).where(LedgerEntry.monitor_ref == ref)).all()
    events = session.exec(
        select(MonitoringEvent).where(MonitoringEvent.monitor_id == user.id)
    ).all()

    # Photographs taken by a person in and around their own community are
    # personal data in practice. They go too. The SHA-256 of each stays on the
    # submission and in the ledger, so the record still proves which image was
    # assessed without holding the image.
    purged = 0
    for e in events:
        if e.photo_sha256 and not e.photo_purged:
            photos.delete(e.photo_sha256)
            if e.marker_sha256:
                photos.delete(e.marker_sha256)
            e.photo_purged = True
            session.add(e)
            purged += 1

    # The row is removed outright rather than blanked. A "deleted" flag on a row
    # that still holds the name is not deletion, it is a promise not to look.
    session.delete(user)
    session.commit()

    return {
        "deleted": {
            "name": True,
            "phone": True,
            "guardian_details": True,
            "consent_record": True,
            "photographs": purged,
        },
        "kept_and_why": [
            {
                "what": f"{len(entries)} stewardship record(s), under {ref}",
                "why": (
                    "These are the environmental record of work that was done "
                    "and paid for. They no longer point at anybody: the "
                    "reference is now a reference to nothing."
                ),
            },
            {
                "what": f"{len(events)} submission record(s): the plot, the date, what the verifier said",
                "why": (
                    "These carry no name and no phone number. They record what "
                    "was found at a plot, which is the thing the project exists "
                    "to establish, and they are now attached to an id that "
                    "belongs to nobody."
                ),
            },
            {
                "what": f"{len(payments)} payment record(s), including the phone number used",
                "why": (
                    "Payment records have to be kept for seven years under "
                    "Kenyan financial rules. We cannot delete these even if we "
                    "want to, and we would rather say so than pretend."
                ),
            },
        ],
        "message": (
            "Your name and number are gone from this system. Nobody can now "
            "look at the public record and find you in it."
        ),
    }
