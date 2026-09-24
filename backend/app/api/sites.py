"""Sites and plots. Readable by anyone; changed only by staff."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Plot, Site, User
from ..schemas import PlotCreate, SiteCreate
from ..services import auth

router = APIRouter(tags=["sites"])


@router.get("/sites", response_model=list[Site])
def list_sites(session: Session = Depends(get_session)) -> list[Site]:
    return session.exec(select(Site)).all()


@router.post("/sites", response_model=Site)
def create_site(
    body: SiteCreate,
    _: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> Site:
    try:
        geom = json.loads(body.geometry_geojson)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "geometry_geojson is not valid JSON") from exc
    if geom.get("type") not in {"Polygon", "MultiPolygon"}:
        raise HTTPException(400, "geometry_geojson must be a Polygon or MultiPolygon")
    site = Site(**body.model_dump(), baseline_source="assumed" if body.baseline_ndvi is not None else None)
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


@router.get("/sites/{site_id}/plots", response_model=list[Plot])
def list_plots(site_id: int, session: Session = Depends(get_session)) -> list[Plot]:
    return session.exec(select(Plot).where(Plot.site_id == site_id)).all()


@router.post("/plots", response_model=Plot)
def create_plot(
    body: PlotCreate,
    _: User = Depends(auth.require_staff),
    session: Session = Depends(get_session),
) -> Plot:
    if session.get(Site, body.site_id) is None:
        raise HTTPException(404, "Site not found")
    if session.exec(select(Plot).where(Plot.code == body.code)).first():
        raise HTTPException(409, "A plot with that code already exists")
    plot = Plot(**body.model_dump())
    session.add(plot)
    session.commit()
    session.refresh(plot)
    return plot
