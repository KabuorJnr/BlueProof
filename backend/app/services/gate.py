"""The verification gate: deterministic rules over a probabilistic assessment.

Every reason a submission is not paid automatically is decided here, in one
pure function, so the rule that moves money can be read, tested and audited
without reading anything else (paper, principle P1).

Three outcomes:
  verified     every check passed; the monitor is paid.
  needs_human  a person must look; nothing is paid until they do.
  rejected     recorded as data, never payable (the plot was already paid for
               this cycle). The observation still counts: a cutting flag on a
               rejected submission still reaches the alerts list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import settings
from ..models import VerificationStatus
from ..schemas import Verdict


@dataclass
class GateInput:
    verdict: Verdict
    has_photo: bool
    distance_m: float | None          # None when the handset sent no GPS fix
    exact_duplicate_of: int | None    # event id sharing the same photo bytes
    near_duplicate_of: int | None     # event id with a perceptually matching photo
    last_paid_at: datetime | None     # most recent paid event on this plot
    now: datetime
    monitor_active: bool
    # Plot marker: None when no marker photo was sent; otherwise the reading.
    marker_sent: bool = False
    marker_code_read: str | None = None
    plot_code: str = ""
    # Comparison with the previous verified visit; None when there is none.
    same_location: str | None = None
    previous_event_id: int | None = None


@dataclass
class GateResult:
    status: VerificationStatus
    reasons: list[str] = field(default_factory=list)

    @property
    def payable(self) -> bool:
        return self.status == VerificationStatus.verified


def cadence_block(last_paid_at: datetime | None, now: datetime) -> str | None:
    if last_paid_at is None or settings.min_days_between_paid_events <= 0:
        return None
    if last_paid_at.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    days = (now - last_paid_at).total_seconds() / 86400
    if days < settings.min_days_between_paid_events:
        return (
            f"This plot was already paid on {last_paid_at:%Y-%m-%d}. One paid "
            f"submission per plot every {settings.min_days_between_paid_events} days; "
            "this one is recorded but not paid."
        )
    return None


def decide(g: GateInput) -> GateResult:
    v = g.verdict

    # Hard stop first: a plot already paid this cycle is never payable,
    # whatever the photograph shows, so there is nothing for a human to decide.
    blocked = cadence_block(g.last_paid_at, g.now)
    if blocked:
        return GateResult(VerificationStatus.rejected, [blocked])

    reasons: list[str] = []
    if not g.monitor_active:
        reasons.append("Monitor account is not yet activated by a CFA lead.")
    if not g.has_photo:
        reasons.append("No photograph. Text-only submissions are never paid automatically.")
    if v.source.startswith("error"):
        reasons.append(f"The verifier failed ({v.source}); a person must assess the photograph.")
    else:
        if not v.legible:
            reasons.append("The verifier judged the photograph not legible enough to assess.")
        if v.health == "unclear":
            reasons.append("Plot condition could not be determined.")
        if v.species_consistent == "no":
            reasons.append(
                f"Species dispute: the image was assessed as {v.detected_species}, "
                "not the declared species. The monitor's declaration stands until a person checks."
            )
        elif v.species_consistent != "yes":
            reasons.append("The verifier could not corroborate the declared species.")
        if v.confidence < settings.min_verification_confidence:
            reasons.append(
                f"Confidence {v.confidence:.2f} is below the {settings.min_verification_confidence:.2f} threshold."
            )
    if g.exact_duplicate_of is not None:
        reasons.append(f"The same photograph was already submitted (event {g.exact_duplicate_of}).")
    elif g.near_duplicate_of is not None:
        reasons.append(f"The photograph closely matches an earlier one (event {g.near_duplicate_of}).")
    if g.marker_sent:
        # The model reads; the comparison is code. An unreadable marker is
        # recorded but does not block: glare and mud are common, and GPS and
        # the other checks still apply. A marker that reads as a DIFFERENT plot
        # is the fraud signal, and that goes to a person.
        if g.marker_code_read and marker_mismatch(g.marker_code_read, g.plot_code):
            reasons.append(
                f"The plot marker reads {g.marker_code_read}, not {g.plot_code}."
            )
    elif settings.require_marker and g.has_photo:
        reasons.append("No plot marker photograph was sent.")
    if g.same_location == "no":
        reasons.append(
            "The photograph does not appear to show the same place as the last "
            f"verified visit (event {g.previous_event_id})."
        )
    if g.distance_m is None:
        if settings.require_gps and g.has_photo:
            reasons.append("No GPS fix was sent with the photograph.")
    elif g.distance_m > settings.geofence_radius_m:
        reasons.append(
            f"Taken {g.distance_m:.0f} m from the registered plot "
            f"(limit {settings.geofence_radius_m:.0f} m)."
        )

    if reasons:
        return GateResult(VerificationStatus.needs_human, reasons)
    return GateResult(VerificationStatus.verified, [])


def normalise_code(code: str | None) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def marker_mismatch(read: str, plot_code: str) -> bool:
    return normalise_code(read) != normalise_code(plot_code)


def review_blockers(last_paid_at: datetime | None, now: datetime, monitor_active: bool) -> list[str]:
    """What still prevents payment when a person approves an escalated event."""
    out = []
    blocked = cadence_block(last_paid_at, now)
    if blocked:
        out.append(blocked)
    if not monitor_active:
        out.append("Monitor account is not active. Activate it first.")
    return out
