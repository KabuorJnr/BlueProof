"""Swahili and Sheng field assistant for community monitors, powered by Llama.

Answers the practical questions a monitor actually has: which species suits
which zone of the creek, spacing, how to record a plot, when payment arrives.
Rule based offline, Llama generated when an endpoint is configured.
"""
from __future__ import annotations

from ..config import settings
from ..schemas import AssistantReply
from . import http

# Planting guidance follows the standard zonation of Kenyan mangrove forests.
ZONATION = (
    "Rhizophora mucronata (mkoko) kwenye maeneo ya chini yanayofurika mara kwa mara; "
    "Avicennia marina (mchu) kwenye maeneo ya juu na chumvi nyingi; "
    "Ceriops tagal (mkandaa) katikati; "
    "Sonneratia alba (mlilana) mbele kabisa ya maji."
)

SYSTEM_PROMPT = (
    "You are the BlueProof field assistant for community mangrove monitors on "
    "the Kenyan coast. Reply in simple Swahili with a little English, short and "
    "practical. Help with which species to plant in which zone, spacing, how to "
    "record a monitoring plot, and when payment arrives. Payment is only "
    "released after a plot photo is verified. Never promise a payment that has "
    f"not been verified. Zonation guidance: {ZONATION}"
)


def _rule_reply(text: str) -> AssistantReply:
    t = text.lower()
    if any(w in t for w in ["panda", "plant", "species", "aina", "wapi"]):
        return AssistantReply(reply=f"Mwongozo wa kupanda: {ZONATION}", intent="planting")
    if any(w in t for w in ["nafasi", "spacing", "umbali"]):
        return AssistantReply(
            reply="Panda miche kwa umbali wa mita 1 hadi 1.5 kati ya mche na mche.",
            intent="spacing",
        )
    if any(w in t for w in ["pesa", "lipa", "malipo", "payment", "lini"]):
        return AssistantReply(
            reply=(
                "Malipo hutumwa kwa M-Pesa baada ya picha yako ya shamba "
                "kuthibitishwa. Ikiwa picha haiko wazi, tutakuomba upige tena."
            ),
            intent="payment",
        )
    if any(w in t for w in ["picha", "photo", "rekodi", "record"]):
        return AssistantReply(
            reply=(
                "Piga picha ukiwa umesimama juu ya shamba, miche ionekane wazi, "
                "mchana wakati wa mwanga mzuri. Hakikisha GPS imewashwa."
            ),
            intent="recording",
        )
    return AssistantReply(
        reply="Karibu BlueProof. Uliza kuhusu kupanda, nafasi, kupiga picha, au malipo.",
        intent="greeting",
    )


async def handle_message(text: str) -> AssistantReply:
    if not settings.llama_api_url:
        return _rule_reply(text)
    try:
        return await _llama_reply(text)
    except Exception:
        # A monitor in the field should never be left without an answer.
        return _rule_reply(text)


async def _llama_reply(text: str) -> AssistantReply:
    payload = {
        "model": settings.llama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {settings.llama_api_key}"} if settings.llama_api_key else {}
    async with http.client(30) as client:
        resp = await client.post(settings.llama_api_url, json=payload, headers=headers)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    return AssistantReply(reply=content.strip(), intent="llama")
