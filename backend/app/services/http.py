"""One place every outbound HTTP call is made from.

Tests replace `transport` with an httpx.MockTransport so the live code paths
for Llama, Copernicus and Daraja run against recorded response shapes without
a network or a credential.
"""
from __future__ import annotations

import httpx

transport: httpx.AsyncBaseTransport | None = None


def client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=transport)
