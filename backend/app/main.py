"""BlueProof API entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from .api import assistant, auth, ledger as ledger_api, monitoring, mrv, payments, privacy, satellite, sites
from .config import settings
from .db import get_session, init_db
from .seed import ensure_seed
from .services import ledger, llama_vision, mpesa, sentinel


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check()
    init_db()
    ensure_seed()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(monitoring.router)
app.include_router(monitoring.review)
app.include_router(satellite.router)
app.include_router(mrv.router)
app.include_router(assistant.router)
app.include_router(payments.router)
app.include_router(privacy.router)
app.include_router(ledger_api.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "app": settings.app_name,
        "status": "ok",
        "environment": settings.environment,
        # "configured", not "live": this reports that an endpoint is set, which
        # is not the same as a call having succeeded, and certainly not the same
        # as the model having been validated on real photographs. The apps show
        # a standing warning whenever this reads "mock", so that nobody
        # demonstrating the system can mistake a deterministic stub for a model.
        "llama": "configured" if llama_vision.is_live() else "mock",
        "llama_model": llama_vision.source_label(),
        "satellite": "sentinel-2" if sentinel.is_live() else "mock",
        "mpesa": settings.mpesa_mode if mpesa.is_live() else "mock",
        "payout_per_verified_event": settings.payout_per_verified_event,
        "min_verification_confidence": settings.min_verification_confidence,
        "geofence_radius_m": settings.geofence_radius_m,
        "min_days_between_paid_events": settings.min_days_between_paid_events,
        "demo_accounts": settings.seed_demo,
        "docs": "/docs",
    }


@app.get("/impact/summary", tags=["impact"])
def impact_summary(session: Session = Depends(get_session)) -> dict:
    return ledger.summary(session)
