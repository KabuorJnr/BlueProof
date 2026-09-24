"""Generate the monitoring, reporting and verification narrative with Llama.

This is the cost killer. Blue carbon standards such as Plan Vivo and Verra
require a structured monitoring narrative, and producing it today consumes
consultant weeks. Here the deterministic facts are assembled in code, and Llama
writes only the narrative around numbers it is handed. It is never asked to
invent a figure.

Offline, a clear template report is produced instead, so the flow still works.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from ..config import settings
from ..models import (
    LedgerEntry,
    MonitoringEvent,
    Plot,
    SatelliteObservation,
    Site,
    VerificationStatus,
)
from . import http, ledger, sentinel

SYSTEM_PROMPT = (
    "You are writing the monitoring section of a community mangrove restoration "
    "report for a blue carbon standard. You will be given verified field "
    "records and satellite observations as structured facts. Write a clear, "
    "sober narrative of what happened at the site in this period. Use only the "
    "figures supplied. Never invent a number, a partner or an outcome. Where "
    "evidence is weak or contradictory, say so plainly. Note any discrepancy "
    "between the field record and the satellite signal. If verified_by_source "
    "or satellite_source includes 'mock', open the report by stating in bold "
    "that it is built on simulated demonstration data and is not evidence. "
    "Keep to about 400 words."
)


def gather_facts(session: Session, site_id: int) -> dict:
    site = session.get(Site, site_id)
    entries = session.exec(select(LedgerEntry).where(LedgerEntry.site_id == site_id)).all()
    obs = session.exec(
        select(SatelliteObservation).where(SatelliteObservation.site_id == site_id)
    ).all()
    # Only this site's submissions. Every flag and rate below is per site.
    events = session.exec(
        select(MonitoringEvent).join(Plot, Plot.id == MonitoringEvent.plot_id).where(Plot.site_id == site_id)
    ).all()
    obs = sorted(obs, key=lambda o: o.observed_on)

    trusted = [o for o in obs if o.cloud_fraction <= sentinel.MAX_TRUSTED_CLOUD]
    alerts = [o for o in trusted if o.alert]
    by_species: dict[str, int] = {}
    for e in entries:
        by_species[e.species] = by_species.get(e.species, 0) + e.seedlings_verified

    return {
        "site": {
            "name": site.name if site else "unknown",
            "county": site.county if site else "unknown",
            "ward": site.ward if site else None,
            "area_ha": site.area_ha if site else 0,
            "baseline_ndvi": site.baseline_ndvi if site else None,
            "baseline_source": (site.baseline_source or "assumed") if site else None,
        },
        "period_end": date.today().isoformat(),
        "verified_events": len(entries),
        "seedlings_verified": sum(e.seedlings_verified for e in entries),
        "seedlings_by_species": by_species,
        "ksh_paid_to_monitors": round(sum(e.amount_paid for e in entries), 0),
        "distinct_monitors": len({e.monitor_ref for e in entries}),
        "submissions": len(events),
        # The abstention rate. The paper's falsification criteria turn on this
        # number, so the report carries it rather than leaving it to be asked.
        "escalated_to_human": sum(1 for e in events if e.reviewed_by is not None or e.status == VerificationStatus.needs_human),
        "approved_by_human": sum(1 for e in events if e.reviewed_by is not None and e.status == VerificationStatus.verified),
        "awaiting_review": sum(1 for e in events if e.status == VerificationStatus.needs_human),
        "verified_by_source": _count(e.verification_source for e in entries),
        "ledger_integrity": "intact" if ledger.verify_chain(session)["ok"] else "BROKEN",
        "cutting_flags": sum(1 for e in events if e.evidence_of_cutting),
        "pest_flags": sum(1 for e in events if e.pest_damage),
        "satellite_observations": len(obs),
        "satellite_usable_after_cloud": len(trusted),
        "satellite_alerts": len(alerts),
        "latest_ndvi_change": trusted[-1].change_vs_baseline if trusted else None,
        "satellite_source": obs[0].source if obs else "none",
    }


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _template_report(f: dict) -> str:
    s = f["site"]
    lines = [
        f"# Monitoring report: {s['name']}",
        "",
    ]
    stubbed = []
    if "mock" in f["verified_by_source"]:
        stubbed.append("field verification")
    if f["satellite_source"] == "mock":
        stubbed.append("satellite observations")
    if stubbed:
        lines += [
            f"**DEMONSTRATION DATA. The {' and '.join(stubbed)} in this report came from "
            "BlueProof's offline simulator, not from a model or from Sentinel-2. Nothing "
            "in it is evidence of anything.**",
            "",
        ]
    lines += [
        f"Site: {s['name']}, {s['ward'] or 'ward not set'}, {s['county']} County. "
        f"Area under monitoring: {s['area_ha']} hectares. Period ending {f['period_end']}.",
        "",
        "## Field record",
        "",
        f"{f['verified_events']} monitoring events were verified in this period, "
        f"covering {f['seedlings_verified']} seedlings recorded by "
        f"{f['distinct_monitors']} community monitors. KSh {f['ksh_paid_to_monitors']:,.0f} "
        "was paid to monitors against verified submissions.",
        "",
        f"Of {f['submissions']} submissions, {f['escalated_to_human']} were escalated to a "
        f"person rather than accepted automatically; {f['approved_by_human']} of those were "
        f"approved on review and {f['awaiting_review']} await review. Verified records by "
        f"verifier: {', '.join(f'{k} {v}' for k, v in f['verified_by_source'].items()) or 'none'}. "
        f"Ledger hash chain: {f['ledger_integrity']}.",
        "",
    ]
    if f["seedlings_by_species"]:
        lines.append("Seedlings verified by species:")
        lines.append("")
        for sp, n in sorted(f["seedlings_by_species"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- {sp}: {n}")
        lines.append("")
    lines += [
        "## Threats observed",
        "",
        f"Evidence of cutting was flagged in {f['cutting_flags']} submissions. "
        f"Pest damage was flagged in {f['pest_flags']} submissions.",
        "",
        "## Satellite corroboration",
        "",
        f"{f['satellite_observations']} observations were retrieved "
        f"({f['satellite_source']}), of which {f['satellite_usable_after_cloud']} were "
        f"usable after cloud screening. {f['satellite_alerts']} sustained canopy loss "
        f"alerts were raised against a baseline NDVI of {s['baseline_ndvi']} "
        f"({s['baseline_source']}).",
    ]
    if f["latest_ndvi_change"] is not None:
        lines.append(
            f"The most recent usable observation shows an NDVI change of "
            f"{f['latest_ndvi_change']} against the site baseline."
        )
    lines += [
        "",
        "## Limitations",
        "",
        "Satellite observation is at 10 metre resolution and detects canopy scale "
        "change only; it cannot resolve individual seedlings, so plot level survival "
        "rests on the field photographs. Cloud cover reduces the usable optical "
        "record. Any carbon figure derived from this report uses an assumed "
        "sequestration rate and must be validated against an approved methodology "
        "before use in a claim.",
        "",
        "_Generated by BlueProof from verified field and satellite records._",
    ]
    return "\n".join(lines)


async def generate(session: Session, site_id: int) -> dict:
    facts = gather_facts(session, site_id)
    if not settings.llama_api_url:
        return {"facts": facts, "narrative": _template_report(facts), "generated_by": "template"}
    try:
        narrative = await _llama_narrative(facts)
        return {"facts": facts, "narrative": narrative, "generated_by": "llama"}
    except Exception as exc:  # never fail the report because the model is down
        return {
            "facts": facts,
            "narrative": _template_report(facts),
            "generated_by": f"template (llama unavailable: {type(exc).__name__})",
        }


async def _llama_narrative(facts: dict) -> str:
    import json

    payload = {
        "model": settings.llama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(facts, indent=2)},
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {settings.llama_api_key}"} if settings.llama_api_key else {}
    async with http.client(90) as client:
        resp = await client.post(settings.llama_api_url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
