"""Canopy scale change detection over a Site.

Deterministic mathematics, no AI. NDVI is computed from Sentinel-2 red (B04) and
near infrared (B08) over the site polygon and compared against a baseline.

Live mode uses the Copernicus Data Space Statistical API, which returns per
interval statistics over a polygon without downloading any raster. Cloud is
screened per pixel with the Sentinel-2 L2A scene classification layer (SCL):
cloud shadow, medium and high probability cloud and thin cirrus are masked out,
and the fraction masked becomes the observation's cloud fraction. An
observation whose cloud fraction exceeds MAX_TRUSTED_CLOUD is stored but never
contributes to an alert (paper, section 4.5).

An alert needs a SUSTAINED drop: the latest trusted observations must all be
below threshold, so a single bad scene (haze the SCL missed, a king tide over
the pneumatophores) does not trigger an enforcement response.

IMPORTANT LIMITATION, keep it in the pitch: Sentinel-2 is 10 metre resolution.
It sees canopy scale loss across a hectare. It cannot see an individual
seedling. Plot level truth comes from the field photographs, not from here.

Without Copernicus credentials this module generates a deterministic, realistic
NDVI series so the alerting logic, the dashboard and the MRV report are all
exercisable offline. Those rows are stored with source "mock".
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from datetime import date, datetime, timedelta, timezone

from ..config import settings
from . import http

# A drop of this much NDVI against baseline is treated as loss.
ALERT_THRESHOLD = -0.08
# Above this cloud fraction an optical observation is not trusted.
MAX_TRUSTED_CLOUD = 0.4
# How many consecutive trusted observations must be below threshold.
SUSTAINED = 2
# Assumed only when nothing has been measured. Mangrove canopy NDVI.
DEFAULT_BASELINE = 0.62

EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
// SCL 3 cloud shadow, 8 cloud medium, 9 cloud high, 10 thin cirrus.
const CLOUD = [3, 8, 9, 10];
function evaluatePixel(s) {
  const clear = s.dataMask === 1 && CLOUD.indexOf(s.SCL) === -1;
  const denom = s.B08 + s.B04;
  const ndvi = denom === 0 ? 0 : (s.B08 - s.B04) / denom;
  return { ndvi: [ndvi], dataMask: [clear ? 1 : 0] };
}
"""

_token: dict = {"value": None, "expires": 0.0}


def is_live() -> bool:
    return bool(settings.copernicus_client_id and settings.copernicus_client_secret)


def apply_alerts(series: list[dict]) -> list[dict]:
    """Mark alerts in place. Only trusted observations count, and only when sustained."""
    run = 0
    for row in series:
        trusted = row["cloud_fraction"] <= MAX_TRUSTED_CLOUD
        row["alert"] = False
        if not trusted:
            continue
        run = run + 1 if row["change_vs_baseline"] <= ALERT_THRESHOLD else 0
        row["alert"] = run >= SUSTAINED
    return series


def _pseudo(seed: str, lo: float, hi: float) -> float:
    d = hashlib.sha256(seed.encode()).digest()
    x = int.from_bytes(d[:4], "big") / 0xFFFFFFFF
    return lo + x * (hi - lo)


def mock_series(site_id: int, baseline: float, days: int = 90, step: int = 5) -> list[dict]:
    """A plausible NDVI history with one degradation event in the recent past."""
    out: list[dict] = []
    today = date.today()
    n = days // step
    for i in range(n):
        observed = today - timedelta(days=(n - 1 - i) * step)
        seed = f"{site_id}:{observed.isoformat()}"
        noise = _pseudo(seed, -0.03, 0.03)
        cloud = round(_pseudo("c" + seed, 0.0, 0.85), 2)

        # Introduce a degradation in the last third of the window so the demo
        # has something real to alert on.
        drop = 0.0
        if i > n * 0.66:
            drop = -0.12 * ((i - n * 0.66) / (n * 0.34))

        ndvi = round(max(0.05, baseline + noise + drop), 3)
        out.append({
            "observed_on": observed,
            "mean_ndvi": ndvi,
            "change_vs_baseline": round(ndvi - baseline, 3),
            "cloud_fraction": cloud,
            "source": "mock",
        })
    return apply_alerts(out)


async def _access_token() -> str:
    if _token["value"] and _token["expires"] > time.time() + 60:
        return _token["value"]
    async with http.client(30) as client:
        resp = await client.post(
            settings.copernicus_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.copernicus_client_id,
                "client_secret": settings.copernicus_client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    _token["value"] = data["access_token"]
    _token["expires"] = time.time() + int(data.get("expires_in", 600))
    return _token["value"]


def stats_request(geometry: dict, start: date, end: date, interval_days: int) -> dict:
    return {
        "input": {
            "bounds": {
                "geometry": geometry,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{end.isoformat()}T23:59:59Z",
            },
            "aggregationInterval": {"of": f"P{interval_days}D"},
            "evalscript": EVALSCRIPT,
            # Degrees, since the bounds are in CRS84. ~10 m at the equator.
            "resx": 0.00009,
            "resy": 0.00009,
        },
        "calculations": {"default": {}},
    }


def parse_stats(body: dict, baseline: float) -> list[dict]:
    """Reduce a Statistical API response to observations.

    Intervals with no acquisition (sampleCount 0) or no clear pixel at all are
    dropped: there is no NDVI to report. Partly cloudy intervals are kept with
    their cloud fraction so the cloud screen is visible in the record.
    """
    out: list[dict] = []
    for item in body.get("data", []):
        if item.get("error"):
            continue
        stats = (
            item.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
        )
        samples = stats.get("sampleCount") or 0
        nodata = stats.get("noDataCount") or 0
        mean = stats.get("mean")
        if samples <= 0 or mean is None or samples == nodata:
            continue
        if isinstance(mean, str):  # the API reports NaN as a string
            continue
        observed = datetime.fromisoformat(item["interval"]["from"].replace("Z", "+00:00")).date()
        ndvi = round(float(mean), 3)
        out.append({
            "observed_on": observed,
            "mean_ndvi": ndvi,
            "change_vs_baseline": round(ndvi - baseline, 3),
            "cloud_fraction": round(nodata / samples, 2),
            "source": "sentinel-2",
        })
    out.sort(key=lambda r: r["observed_on"])
    return apply_alerts(out)


async def _statistics(geometry_geojson: str, start: date, end: date, interval_days: int) -> dict:
    token = await _access_token()
    body = stats_request(json.loads(geometry_geojson), start, end, interval_days)
    async with http.client(120) as client:
        resp = await client.post(
            settings.copernicus_stats_url,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_series(site_id: int, baseline: float, geometry_geojson: str) -> list[dict]:
    if not is_live():
        return mock_series(site_id, baseline)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=settings.satellite_lookback_days)
    body = await _statistics(geometry_geojson, start, end, settings.satellite_interval_days)
    return parse_stats(body, baseline)


async def measure_baseline(geometry_geojson: str, start: date, end: date) -> dict:
    """Median NDVI of trusted observations over a reference window.

    A baseline should be measured, not assumed: an AOI polygon that includes
    open water or mudflat has a much lower mean NDVI than a closed canopy, and
    comparing it to a textbook canopy value raises a permanent false alert.
    """
    if not is_live():
        return {"baseline_ndvi": DEFAULT_BASELINE, "observations": 0, "source": "assumed (mock mode)"}
    body = await _statistics(geometry_geojson, start, end, settings.satellite_interval_days)
    rows = [r for r in parse_stats(body, 0.0) if r["cloud_fraction"] <= MAX_TRUSTED_CLOUD]
    if not rows:
        raise ValueError("No cloud-free observations in that window; widen it.")
    return {
        "baseline_ndvi": round(statistics.median(r["mean_ndvi"] for r in rows), 3),
        "observations": len(rows),
        "source": f"sentinel-2 median {start.isoformat()}..{end.isoformat()}",
    }
