"""Test harness.

Each test gets a fresh database and photo store. Outbound HTTP is routed
through `services.http.transport`, so the live Llama, Copernicus and Daraja
code paths run against canned responses shaped like the real APIs.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="blueproof-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["PHOTO_DIR"] = str(_TMP / "photos")
os.environ["DEMO_SEED"] = "true"
os.environ["ENVIRONMENT"] = "dev"
# Tests never reach a real service, whatever backend/.env holds: environment
# variables take precedence over the file, and blanks mean mock mode.
for _name in ("LLAMA_API_URL", "LLAMA_API_KEY", "COPERNICUS_CLIENT_ID", "COPERNICUS_CLIENT_SECRET"):
    os.environ[_name] = ""
os.environ["MPESA_MODE"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import ensure_seed  # noqa: E402
from app.services import http, mpesa, sentinel  # noqa: E402

# Seeded plot TC-A-001 and a point ~20 m from it.
PLOT = {"id": 1, "species": "Rhizophora mucronata", "lat": -4.018, "lon": 39.664}
NEAR = {"lat": "-4.01815", "lon": "39.66410"}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    ensure_seed()
    shutil.rmtree(settings.photo_dir, ignore_errors=True)
    http.transport = None
    mpesa._token.update(value=None, expires=0.0)
    sentinel._token.update(value=None, expires=0.0)
    yield
    http.transport = None


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, phone: str, pin: str) -> dict:
    r = client.post("/auth/login", json={"phone": phone, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def amina(client):
    return login(client, "254712000001", "1111")


@pytest.fixture
def juma(client):
    return login(client, "254712000002", "2222")


@pytest.fixture
def lead(client):
    return login(client, "254712000003", "3333")


@pytest.fixture
def admin(client):
    return login(client, "254712000009", "9999")


def photo(seed: int = 0, size=(640, 480)) -> bytes:
    """A distinct random image per seed, so hashes and dHashes differ."""
    import random

    rnd = random.Random(seed)
    img = Image.frombytes("RGB", size, bytes(rnd.getrandbits(8) for _ in range(size[0] * size[1] * 3)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def submit(client, headers, img: bytes | None, **form) -> httpx.Response:
    data = {"plot_id": str(PLOT["id"]), **NEAR, **form}
    data = {k: v for k, v in data.items() if v is not None}
    files = {"image": ("plot.jpg", img, "image/jpeg")} if img is not None else None
    return client.post("/monitoring/submit-photo", data=data, files=files, headers=headers)


def model_reply(reply: dict | str, status: int = 200):
    """Point the verifier at a fake OpenAI-compatible endpoint returning `reply`."""
    settings.llama_api_url = "https://llm.test/v1/chat/completions"
    settings.llama_api_key = "test"
    content = reply if isinstance(reply, str) else json.dumps(reply)
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": "boom"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    http.transport = httpx.MockTransport(handler)
    return seen


def model_router(verify=None, marker=None, compare=None, verify_sequence=None, status=200):
    """A fake endpoint that answers by which prompt it was sent.

    verify_sequence, if given, is a list of replies (dict, str, or an int HTTP
    status) handed out in order to successive verifier calls.
    """
    settings.llama_api_url = "https://llm.test/v1/chat/completions"
    settings.llama_api_key = "test"
    seen: dict[str, list] = {"verify": [], "marker": [], "compare": []}
    queue = list(verify_sequence or [])

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        kind = "marker" if "plot marker" in system else "compare" if "side by side" in system else "verify"
        seen[kind].append(body)
        if status != 200:
            return httpx.Response(status, json={"error": "boom"})
        reply = {"verify": verify, "marker": marker, "compare": compare}[kind]
        if kind == "verify" and queue:
            reply = queue.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": "boom"})
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    http.transport = httpx.MockTransport(handler)
    return seen


GOOD = {
    "legible": True, "health": "healthy", "cutting": False, "pests": False,
    "species_consistent": "yes", "species_if_different": None, "seedlings": 14,
    "confidence": 0.86, "reasoning": "Fourteen upright Rhizophora seedlings, green leaves.",
}


@pytest.fixture
def live_model(monkeypatch):
    monkeypatch.setattr(settings, "llama_api_url", None)
    monkeypatch.setattr(settings, "llama_api_key", None)
    return model_reply
