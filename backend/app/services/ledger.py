"""The verified stewardship ledger and the impact rollup.

Every entry is written only after a MonitoringEvent is verified AND its payment
has settled. This is the record a blue carbon project, a funder or a buyer pays
for, because it ties a place, a date, a species, the evidence hash and a payment
together in one line. The monitor appears as a pseudonymous reference, never a
name.

The ledger is hash chained. Each entry's hash covers its own content and the
previous entry's hash, so editing or deleting any line invalidates every line
after it. That does not make tampering impossible for someone with database
access; it makes it detectable by anyone holding an earlier export, which is
the property an auditor needs.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..config import settings
from ..models import LedgerEntry, MonitoringEvent, Plot, Site, User, VerificationStatus

_lock = threading.Lock()

_HASHED = (
    "monitoring_event_id", "site_id", "plot_code", "species", "seedlings_verified",
    "health", "monitor_ref", "amount_paid", "verification_source", "reviewed_by_ref",
    "photo_sha256", "mpesa_receipt", "lat", "lon",
)


def _ts(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat()


def compute_hash(entry: LedgerEntry) -> str:
    body = {k: getattr(entry, k) for k in _HASHED}
    body["recorded_at"] = _ts(entry.recorded_at)
    body["prev_hash"] = entry.prev_hash
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_entry(
    session: Session,
    event: MonitoringEvent,
    amount_paid: float,
    mpesa_receipt: str | None = None,
) -> LedgerEntry:
    existing = session.exec(
        select(LedgerEntry).where(LedgerEntry.monitoring_event_id == event.id)
    ).first()
    if existing is not None:
        return existing

    plot = session.get(Plot, event.plot_id)
    monitor = session.get(User, event.monitor_id)
    reviewer = session.get(User, event.reviewed_by) if event.reviewed_by else None

    with _lock:
        last = session.exec(select(LedgerEntry).order_by(LedgerEntry.id.desc())).first()
        entry = LedgerEntry(
            monitoring_event_id=event.id,
            site_id=plot.site_id,
            plot_code=plot.code,
            # The monitor's declaration where the verifier corroborated it or a
            # person approved it. The model's alternative never overwrites it.
            species=event.reported_species or plot.species,
            seedlings_verified=event.seedlings_visible or 0,
            health=event.health or "unclear",
            monitor_ref=(monitor.public_ref or f"BP-M-{monitor.id:04d}") if monitor else "unknown",
            amount_paid=float(amount_paid),
            verification_source=event.verification_source or "unknown",
            reviewed_by_ref=reviewer.public_ref if reviewer else None,
            photo_sha256=event.photo_sha256,
            mpesa_receipt=mpesa_receipt,
            lat=event.lat if event.lat is not None else plot.lat,
            lon=event.lon if event.lon is not None else plot.lon,
            recorded_at=datetime.now(timezone.utc).replace(microsecond=0),
            prev_hash=last.entry_hash if last else "",
        )
        entry.entry_hash = compute_hash(entry)
        session.add(entry)
        session.commit()
        session.refresh(entry)
    return entry


def verify_chain(session: Session) -> dict:
    entries = session.exec(select(LedgerEntry).order_by(LedgerEntry.id)).all()
    prev = ""
    for e in entries:
        if e.prev_hash != prev:
            return {
                "ok": False, "entries": len(entries), "first_bad_id": e.id,
                "problem": "prev_hash does not match the entry before it: a line was removed or reordered",
            }
        if compute_hash(e) != e.entry_hash:
            return {
                "ok": False, "entries": len(entries), "first_bad_id": e.id,
                "problem": "content does not match its hash: this line was edited",
            }
        prev = e.entry_hash
    return {"ok": True, "entries": len(entries), "head": prev or None}


def summary(session: Session) -> dict:
    entries = session.exec(select(LedgerEntry)).all()
    sites = session.exec(select(Site)).all()
    events = session.exec(select(MonitoringEvent)).all()

    hectares = sum(s.area_ha for s in sites)
    seedlings = sum(e.seedlings_verified for e in entries)
    paid = sum(e.amount_paid for e in entries)
    by_species: dict[str, int] = {}
    for e in entries:
        by_species[e.species] = by_species.get(e.species, 0) + e.seedlings_verified

    sources: dict[str, int] = {}
    for e in entries:
        sources[e.verification_source] = sources.get(e.verification_source, 0) + 1

    return {
        "hectares_under_monitoring": round(hectares, 2),
        "submissions": len(events),
        "verified_events": len(entries),
        "awaiting_review": sum(1 for e in events if e.status == VerificationStatus.needs_human),
        "seedlings_verified": seedlings,
        "ksh_paid_to_monitors": round(paid, 0),
        "ksh_per_verified_event": settings.payout_per_verified_event,
        "monitors_active": len({e.monitor_ref for e in entries}),
        "cutting_alerts": sum(1 for e in events if e.evidence_of_cutting),
        "pest_alerts": sum(1 for e in events if e.pest_damage),
        # Indicative only. See config.co2_tonnes_per_ha_year: this is an
        # assumption awaiting validation, not a measured sequestration figure.
        "indicative_co2_tonnes_per_year": round(hectares * settings.co2_tonnes_per_ha_year, 1),
        "co2_basis": (
            f"{settings.co2_tonnes_per_ha_year} t CO2 per ha per year, ASSUMPTION, "
            "validate with KMFRI or a Plan Vivo methodology before quoting"
        ),
        "seedlings_by_species": by_species,
        "verified_by_source": sources,
    }
