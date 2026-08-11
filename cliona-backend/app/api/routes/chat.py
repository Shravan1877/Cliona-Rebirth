from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.models.schemas import ChatRequest

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream per CLAUDE.md §12.3: resolve user, create/verify the
    conversation, consume pending_persona, run retrieve + assemble nodes,
    stream the LLM response, then fire the background task (§12.4).
    """
    raise NotImplementedError("Phase 1")
