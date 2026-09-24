"""Sign in, who am I, and the staff controls over accounts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Payment, PaymentStatus, Role, User
from ..services import auth

router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    phone: str
    pin: str


def public_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "public_ref": user.public_ref,
        "role": user.role,
        "cfa": user.cfa,
        "active": user.active,
    }


@router.post("/auth/login")
def login(body: LoginBody, session: Session = Depends(get_session)) -> dict:
    phone = body.phone.strip().replace(" ", "")
    user = session.exec(select(User).where(User.phone == phone)).first()
    token = auth.login(session, user, body.pin.strip())
    return {"token": token, "user": public_user(user)}


@router.get("/auth/me")
def me(user: User = Depends(auth.current_user), session: Session = Depends(get_session)) -> dict:
    payments = session.exec(select(Payment).where(Payment.user_id == user.id)).all()
    return {
        **public_user(user),
        "earned_ksh": round(sum(p.amount for p in payments if p.status == PaymentStatus.success), 0),
        "pending_ksh": round(sum(p.amount for p in payments if p.status == PaymentStatus.pending), 0),
        "payments": len(payments),
    }


@router.get("/users")
def list_users(
    _: User = Depends(auth.require_staff), session: Session = Depends(get_session)
) -> list[dict]:
    """Everyone enrolled, with the inactive ones a CFA lead still has to approve."""
    users = session.exec(select(User).order_by(User.active, User.id)).all()
    return [{**public_user(u), "phone": u.phone, "is_minor": u.is_minor} for u in users]


class ActivateBody(BaseModel):
    active: bool = True


@router.post("/users/{user_id}/activate")
def activate(
    user_id: int,
    body: ActivateBody,
    staff: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> dict:
    """A CFA lead confirms this is a real member of the group, or suspends them."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "No such person")
    if user.role == Role.admin and staff.role != Role.admin:
        raise HTTPException(403, "Only an admin can change an admin account.")
    user.active = body.active
    session.add(user)
    session.commit()
    return public_user(user)


class RoleBody(BaseModel):
    role: Role


@router.post("/users/{user_id}/role")
def set_role(
    user_id: int,
    body: RoleBody,
    _: User = Depends(auth.require_admin),
    session: Session = Depends(get_session),
) -> dict:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "No such person")
    user.role = body.role
    session.add(user)
    session.commit()
    return public_user(user)


class PinReset(BaseModel):
    pin: str


@router.post("/users/{user_id}/pin")
def reset_pin(
    user_id: int,
    body: PinReset,
    staff: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> dict:
    """In person reset by a CFA lead, for the monitor who forgot their PIN."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "No such person")
    if user.role != Role.monitor and staff.role != Role.admin:
        raise HTTPException(403, "Only an admin can reset a staff PIN.")
    if not auth.valid_pin(body.pin):
        raise HTTPException(400, "PIN must be 4 to 8 digits.")
    user.pin_hash = auth.hash_pin(body.pin)
    user.failed_logins = 0
    user.locked_until = None
    session.add(user)
    session.commit()
    return {"ok": True}
