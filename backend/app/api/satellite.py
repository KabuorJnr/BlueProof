"""Satellite canopy change for a site."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..db import get_session
from ..models import SatelliteObservation, Site, User
from ..services import auth, sentinel

router = APIRouter(prefix="/satellite", tags=["satellite"])


@router.post("/refresh/{site_id}")
async def refresh(
    site_id: int,
    _: User = Depends(auth.current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Pull the NDVI series for a site and store it, replacing what was there."""
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")
    baseline = site.baseline_ndvi if site.baseline_ndvi is not None else sentinel.DEFAULT_BASELINE

    try:
        series = await sentinel.fetch_series(site_id, baseline, site.geometry_geojson)
    except Exception as exc:
        # Keep the previous series rather than replacing it with nothing.
        raise HTTPException(502, f"Satellite source unavailable: {type(exc).__name__}: {exc}") from exc

    session.exec(delete(SatelliteObservation).where(SatelliteObservation.site_id == site_id))
    for row in series:
        session.add(SatelliteObservation(site_id=site_id, **row))
    session.commit()

    usable = [r for r in series if r["cloud_fraction"] <= sentinel.MAX_TRUSTED_CLOUD]
    alerts = [r for r in usable if r["alert"]]
    return {
        "site": site.name,
        "mode": "sentinel-2" if sentinel.is_live() else "mock",
        "baseline_ndvi": baseline,
        "baseline_source": site.baseline_source or "assumed",
        "observations": len(series),
        "usable_after_cloud": len(usable),
        "alerts": len(alerts),
        "latest_change_vs_baseline": usable[-1]["change_vs_baseline"] if usable else None,
        "note": (
            "10 metre resolution detects canopy scale loss only, not individual "
            "seedlings. Plot level truth comes from field photographs."
        ),
    }


class BaselineWindow(BaseModel):
    start: date
    end: date


@router.post("/baseline/{site_id}")
async def measure_baseline(
    site_id: int,
    window: BaselineWindow,
    _: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> dict:
    """Measure the site baseline as the median clear-sky NDVI over a reference window.

    Use a window before restoration or loss began, ideally a full year so that
    seasonality averages out.
    """
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(404, "Site not found")
    if window.end <= window.start:
        raise HTTPException(400, "end must be after start")
    try:
        result = await sentinel.measure_baseline(site.geometry_geojson, window.start, window.end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Satellite source unavailable: {type(exc).__name__}: {exc}") from exc
    if sentinel.is_live():
        site.baseline_ndvi = result["baseline_ndvi"]
        site.baseline_source = result["source"]
        session.add(site)
        session.commit()
    return result


@router.get("/{site_id}", response_model=list[SatelliteObservation])
def series(site_id: int, session: Session = Depends(get_session)) -> list[SatelliteObservation]:
    return session.exec(
        select(SatelliteObservation)
        .where(SatelliteObservation.site_id == site_id)
        .order_by(SatelliteObservation.observed_on)
    ).all()
