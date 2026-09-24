"""Seed data and the production bootstrap.

Demo mode seeds a Tudor Creek site with fictional people whose PINs are
printed below, so that anybody can sign in to a demo. It is off by default in
production. A production deployment instead creates one admin from
ADMIN_PHONE and ADMIN_PIN, once, and everybody else is enrolled through the
consent flow.

Coordinates are indicative only. Replace with a real boundary agreed with the
Kenya Forest Service and the local Community Forest Association before any
field pilot.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Plot, Role, Site, User
from .services import auth

TUDOR_CREEK_GEOJSON = (
    '{"type":"Polygon","coordinates":[[[39.650,-4.030],[39.700,-4.030],'
    '[39.700,-4.000],[39.650,-4.000],[39.650,-4.030]]]}'
)

# Demo credentials. Public on purpose; never used outside demo mode.
DEMO_PEOPLE = [
    # name, phone, role, pin, public_ref
    ("Amina Hassan", "254712000001", Role.monitor, "1111", "BP-M-0001"),
    ("Juma Otieno", "254712000002", Role.monitor, "2222", "BP-M-0002"),
    ("Mwanaisha Said", "254712000003", Role.cfa_lead, "3333", "BP-M-0003"),
    ("Demo Admin", "254712000009", Role.admin, "9999", "BP-A-0009"),
]


def ensure_seed() -> None:
    with Session(engine) as session:
        if settings.seed_demo:
            _seed_demo(session)
        _bootstrap_admin(session)


def _bootstrap_admin(session: Session) -> None:
    if not (settings.admin_phone and settings.admin_pin):
        return
    if session.exec(select(User).where(User.role == Role.admin)).first():
        return
    if not auth.valid_pin(settings.admin_pin):
        raise RuntimeError("ADMIN_PIN must be 4 to 8 digits")
    admin = User(
        name=settings.admin_name,
        phone=settings.admin_phone,
        role=Role.admin,
        active=True,
        pin_hash=auth.hash_pin(settings.admin_pin),
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    admin.public_ref = f"BP-A-{admin.id:04d}"
    session.add(admin)
    session.commit()


def _seed_demo(session: Session) -> None:
    if session.exec(select(Site)).first():
        return

    site = Site(
        name="Tudor Creek",
        county="Mombasa",
        ward="Tudor",
        area_ha=42.0,
        geometry_geojson=TUDOR_CREEK_GEOJSON,
        baseline_ndvi=0.62,
        baseline_source="assumed",
    )
    session.add(site)
    session.commit()
    session.refresh(site)

    # Seed people are fictional. Real monitors are enrolled through the
    # consent flow, which is the only place a name legitimately enters the
    # system, and each of them gets a public_ref at that moment.
    session.add_all([
        User(name=name, phone=phone, role=role, cfa="Tudor CFA", public_ref=ref,
             active=True, pin_hash=auth.hash_pin(pin))
        for name, phone, role, pin, ref in DEMO_PEOPLE
    ])

    session.add_all([
        Plot(site_id=site.id, code="TC-A-001", species="Rhizophora mucronata",
             seedlings_planted=120, planted_on=date(2026, 5, 12), lat=-4.018, lon=39.664),
        Plot(site_id=site.id, code="TC-A-002", species="Avicennia marina",
             seedlings_planted=90, planted_on=date(2026, 5, 19), lat=-4.014, lon=39.671),
        Plot(site_id=site.id, code="TC-B-007", species="Sonneratia alba",
             seedlings_planted=60, planted_on=date(2026, 6, 2), lat=-4.009, lon=39.678),
    ])
    session.commit()
