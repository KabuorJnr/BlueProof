"""Monitoring, reporting and verification output."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Site
from ..services import mrv_report

router = APIRouter(prefix="/mrv", tags=["mrv"])


@router.get("/report/{site_id}")
async def report(site_id: int, session: Session = Depends(get_session)) -> dict:
    """Assemble verified facts and have Llama write the monitoring narrative."""
    if session.get(Site, site_id) is None:
        raise HTTPException(404, "Site not found")
    return await mrv_report.generate(session, site_id)


@router.get("/facts/{site_id}")
def facts(site_id: int, session: Session = Depends(get_session)) -> dict:
    """The deterministic facts only, with no narrative. Useful for auditors."""
    if session.get(Site, site_id) is None:
        raise HTTPException(404, "Site not found")
    return mrv_report.gather_facts(session, site_id)
