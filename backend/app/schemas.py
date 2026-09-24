"""Request and response shapes."""
from __future__ import annotations

from pydantic import BaseModel


class Verdict(BaseModel):
    """What the verifier concluded from a field photograph.

    `source` is not decoration. An attestation whose provenance is unknown is
    not an attestation, and this system can produce a verdict from a
    deterministic stub that looks exactly like a model's. The stub is honest
    about itself only if that honesty is carried through every layer that
    stores, displays or sells the result, so the field is required and there is
    no default.
    """
    source: str                    # "mock", "<model>@<prompt version>", or "error:..."
    legible: bool
    species_consistent: str        # yes | no | unclear, against the DECLARED species
    detected_species: str          # the declared species if consistent, else the alternative or "unclear"
    seedlings_visible: int
    health: str                    # healthy | stressed | dead | unclear
    evidence_of_cutting: bool
    pest_damage: bool
    # With sampling, the share of samples that agreed. Without, what the
    # model said about itself.
    confidence: float
    reasoning: str
    self_reported_confidence: float | None = None
    samples: int = 1


class SiteCreate(BaseModel):
    name: str
    county: str
    ward: str | None = None
    area_ha: float
    geometry_geojson: str
    baseline_ndvi: float | None = None


class PlotCreate(BaseModel):
    site_id: int
    code: str
    species: str
    seedlings_planted: int = 0
    lat: float
    lon: float


class AssistantMessage(BaseModel):
    text: str


class AssistantReply(BaseModel):
    reply: str
    intent: str
