"""[B9] GET /v1/conversations, GET /v1/conversations/{id}/messages.
User is resolved from the JWT — no user_id path param on either route.
"""

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user

router = APIRouter(prefix="/v1", tags=["conversations"])


@router.get("/conversations")
async def list_conversations(user_id: str = Depends(get_current_user)) -> list:
    raise NotImplementedError("Phase 1")


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
) -> list:
    """Ownership-checked: conversation_id must belong to the resolved user_id."""
    raise NotImplementedError("Phase 1")
