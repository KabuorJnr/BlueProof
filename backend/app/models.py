"""Database models for BlueProof.

The chain of custody: a Site holds Plots, a Plot receives MonitoringEvents, a
verified MonitoringEvent triggers a Payment and writes a LedgerEntry. Satellite
observations sit against the Site and corroborate, or contradict, the field
record.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    monitor = "monitor"          # community youth doing the field work
    cfa_lead = "cfa_lead"        # Community Forest Association lead
    verifier = "verifier"        # KFS, KMFRI or project verifier
    admin = "admin"


# Roles allowed to review escalated submissions and see the operational record.
STAFF_ROLES = (Role.cfa_lead, Role.verifier, Role.admin)


class VerificationStatus(str, Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    needs_human = "needs_human"   # low confidence, escalate to a person


class PaymentStatus(str, Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str = Field(index=True, unique=True, description="M-Pesa number, format 2547XXXXXXXX")
    role: Role = Role.monitor
    cfa: str | None = Field(default=None, description="Community Forest Association")

    # A stable pseudonym used everywhere the record leaves this system. The name
    # and the phone number stay in this table, which is the only place a person
    # is identifiable, and which is what a deletion request empties.
    public_ref: str = Field(default="", index=True, description="e.g. BP-M-0007")

    # Sign in. A PIN rather than a password because the people using this are
    # on a creek edge with a cheap handset, and rather than an SMS code because
    # that needs a paid provider before the first plot is photographed.
    pin_hash: str | None = None
    failed_logins: int = 0
    locked_until: datetime | None = None
    # Self-enrolled monitors wait for a CFA lead to activate them. An inactive
    # account can sign in and see its own record but cannot be paid.
    active: bool = False

    # Consent, recorded rather than assumed. A tick in a form that leaves no
    # trace is not consent anybody can later demonstrate, and the Data
    # Protection Act puts the burden of demonstrating it on the controller.
    consent_version: str | None = None
    consented_at: datetime | None = None

    # Set only where the monitor is under 18. Holding the guardian's name and
    # number is the minimum that makes guardian consent real; the monitor's own
    # date of birth is deliberately NOT stored, because the system never needs
    # to know an age, only whether a guardian had to consent.
    is_minor: bool = False
    guardian_name: str | None = None
    guardian_phone: str | None = None

    created_at: datetime = Field(default_factory=_now)


class Site(SQLModel, table=True):
    """A monitored mangrove area of interest."""
    id: int | None = Field(default=None, primary_key=True)
    name: str
    county: str
    ward: str | None = None
    area_ha: float
    # GeoJSON polygon as text. Kept as text to avoid a PostGIS dependency in the MVP.
    geometry_geojson: str
    baseline_ndvi: float | None = None
    # Where the baseline came from: "assumed", or the window it was measured over.
    baseline_source: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Plot(SQLModel, table=True):
    """A planting or protection plot inside a Site."""
    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    code: str = Field(index=True, unique=True, description="Field code, e.g. TC-A-014")
    species: str = Field(description="e.g. Rhizophora mucronata, Avicennia marina")
    seedlings_planted: int = 0
    planted_on: date | None = None
    lat: float
    lon: float
    created_at: datetime = Field(default_factory=_now)


class MonitoringEvent(SQLModel, table=True):
    """One field submission: a geotagged photo and what the verifier made of it."""
    id: int | None = Field(default=None, primary_key=True)
    plot_id: int = Field(foreign_key="plot.id", index=True)
    monitor_id: int = Field(index=True)

    # Idempotency key generated on the handset. An offline queue that retries
    # after a lost response must not be paid twice for one photograph.
    client_ref: str | None = Field(default=None, index=True, unique=True)

    # The evidence. The photo is stored under its SHA-256, which is also what
    # the ledger carries, so a ledger line can be matched to the exact bytes
    # that were assessed even after the image itself is purged.
    photo_ref: str | None = None
    photo_sha256: str | None = Field(default=None, index=True)
    photo_dhash: str | None = None
    photo_purged: bool = False

    # The plot marker photograph (protocol shot 1) and what the model read on it.
    marker_sha256: str | None = None
    marker_code_read: str | None = None
    marker_matches: bool | None = None

    # Comparison with the last verified photograph of this plot.
    previous_event_id: int | None = None
    same_location: str | None = None        # yes | no | unclear
    change_vs_previous: str | None = None   # improved | unchanged | declined | unclear
    change_note: str | None = None

    reported_species: str | None = None
    reported_survival: int | None = Field(default=None, description="seedlings alive, as reported")
    lat: float | None = None
    lon: float | None = None
    distance_from_plot_m: float | None = None

    # Verifier verdict
    status: VerificationStatus = VerificationStatus.pending
    # Which verifier answered: "mock", or the model identifier. Nullable only so
    # that rows written before this column existed can still be read; every new
    # row sets it.
    verification_source: str | None = None
    legible: bool | None = None
    species_consistent: str | None = None   # yes | no | unclear
    detected_species: str | None = None
    seedlings_visible: int | None = None
    health: str | None = Field(default=None, description="healthy | stressed | dead | unclear")
    evidence_of_cutting: bool = False
    pest_damage: bool = False
    # With sampling, the share of samples that agreed on the gated answers.
    confidence: float = 0.0
    self_reported_confidence: float | None = None
    verifier_samples: int = 1
    reasoning: str | None = None
    # JSON list of the reasons the gate declined to auto-verify. Empty when it
    # did. A reviewer needs to know why a submission is in front of them.
    review_reasons: str = "[]"

    # Human review, when the gate escalated.
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None

    created_at: datetime = Field(default_factory=_now)
    verified_at: datetime | None = None


class SatelliteObservation(SQLModel, table=True):
    """Canopy scale signal for a Site. Corroborates the field record."""
    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    observed_on: date
    mean_ndvi: float
    change_vs_baseline: float
    cloud_fraction: float = 0.0
    alert: bool = False
    source: str = "mock"          # mock | sentinel-2
    created_at: datetime = Field(default_factory=_now)


class Payment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # Unique: one payment per event, whatever path releases it and however
    # many times a reviewer double clicks.
    monitoring_event_id: int = Field(foreign_key="monitoringevent.id", index=True, unique=True)
    user_id: int = Field(index=True)
    phone: str
    amount: float
    status: PaymentStatus = PaymentStatus.pending
    # Our OriginatorConversationID, sent to Daraja and echoed on the result.
    mpesa_ref: str | None = Field(default=None, index=True)
    # Safaricom's M-Pesa receipt (TransactionID) once the money has moved.
    mpesa_receipt: str | None = None
    failure_reason: str | None = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=_now)
    settled_at: datetime | None = None


class LedgerEntry(SQLModel, table=True):
    """Verified stewardship record. This is the product buyers pay for.

    Append-only and hash chained: every entry commits to the one before it, so
    altering or deleting any line breaks every line after it, and
    `GET /ledger/verify` says exactly where.
    """
    id: int | None = Field(default=None, primary_key=True)
    monitoring_event_id: int = Field(foreign_key="monitoringevent.id", index=True, unique=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    plot_code: str
    species: str
    seedlings_verified: int
    health: str
    # A pseudonym, not a name.
    #
    # This table is the product. It is exported, shown to funders, and sold to
    # credit buyers, and it already carries a plot code, a date and coordinates
    # accurate to a few metres. Adding a real name to those three turns an
    # environmental record into a published statement of where an identifiable
    # young person was on a given morning, for every morning they worked.
    #
    # The pseudonym preserves everything the record needs: a buyer can still see
    # that one person monitored these plots consistently, an auditor can still
    # follow a disputed entry back through `user.public_ref`. What it removes is
    # the ability of anyone holding an exported spreadsheet to do the same.
    monitor_ref: str
    amount_paid: float
    # Carried into the ledger deliberately. This table is the thing a funder or
    # a credit buyer is asked to trust, and a line that does not say what
    # verified it cannot be audited. A ledger full of "mock" is a demo; the
    # distinction has to survive being exported to a spreadsheet.
    verification_source: str = "unknown"
    # Pseudonym of the person who approved an escalated submission, if any.
    reviewed_by_ref: str | None = None
    photo_sha256: str | None = None
    mpesa_receipt: str | None = None
    lat: float | None = None
    lon: float | None = None
    recorded_at: datetime = Field(default_factory=_now)
    prev_hash: str = ""
    entry_hash: str = Field(default="", index=True)
