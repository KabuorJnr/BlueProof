"""Field assistant endpoint for monitors.

Signed in only: every message may cost a model call, and an open endpoint that
spends money per request is an invitation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import User
from ..schemas import AssistantMessage, AssistantReply
from ..services import auth, field_assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/message", response_model=AssistantReply)
async def message(body: AssistantMessage, _: User = Depends(auth.current_user)) -> AssistantReply:
    """Wire this to the WhatsApp Business API or Africa's Talking in production."""
    return await field_assistant.handle_message(body.text[:1000])
