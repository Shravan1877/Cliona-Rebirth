"""POST /v1/chat — non-streaming implementation (Phase 6, CLAUDE.md §12.2/§12.3).

Wires auth (Phase 3), the retrieve/assemble/generate nodes (Phase 5), and the
LLM factory (Phase 4) into a real HTTP endpoint. Deliberately excludes SSE
streaming (Phase 7), the pending_persona/turn_count read-write lifecycle
(Phase 8), and background classification + embedding write-back (Phase 9).
persona_to_inject here is just session_state.current_persona as it already
stands — always None until Phase 8 ever writes it, which is fine per [B1]:
turn 1 (and every turn until Phase 8 exists) correctly injects no persona.
"""

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.core.auth import get_current_user
from app.core.database import AsyncSessionLocal
from app.graph.nodes import assemble_prompt_node, generate_node, retrieve_memory_node
from app.models.schemas import ChatRequest
from app.services.session_manager import get_session_state

router = APIRouter(prefix="/v1", tags=["chat"])

TITLE_MAX_LEN = 50


def _generate_title(message: str) -> str:
    """First user message truncated to ~50 chars on a word boundary, with
    '…' appended if truncated. No new column, no LLM call (§3.3).
    """
    message = message.strip()
    if len(message) <= TITLE_MAX_LEN:
        return message or "New Conversation"

    truncated = message[:TITLE_MAX_LEN]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "…"


async def _create_conversation(user_id: str, first_message: str) -> tuple[str, Dict[str, Any]]:
    """Inserts conversations + session_state in one transaction (§12.2/[A5])."""
    title = _generate_title(first_message)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            conv_result = await session.execute(
                text(
                    """
                    INSERT INTO conversations (user_id, title)
                    VALUES (:user_id, :title)
                    RETURNING id
                    """
                ),
                {"user_id": user_id, "title": title},
            )
            conversation_id = str(conv_result.scalar_one())

            await session.execute(
                text(
                    """
                    INSERT INTO session_state
                        (conversation_id, user_id, turn_count, current_persona, pending_persona, last_3_messages)
                    VALUES
                        (:conversation_id, :user_id, 0, NULL, NULL, '[]'::jsonb)
                    """
                ),
                {"conversation_id": conversation_id, "user_id": user_id},
            )

    session_state = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "turn_count": 0,
        "current_persona": None,
        "pending_persona": None,
        "last_3_messages": [],
    }
    return conversation_id, session_state


async def _check_conversation_ownership(user_id: str, conversation_id: str) -> None:
    """Nonexistent conversation_id -> 404. Belongs to a different user -> 403 (§3.8)."""
    try:
        UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT user_id FROM conversations WHERE id = :conversation_id"),
            {"conversation_id": conversation_id},
        )
        row = result.mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(row["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Conversation does not belong to the authenticated user")


async def _persist_messages(
    conversation_id: str, user_id: str, user_message: str, assistant_message: str
) -> None:
    """Inserts both messages, no embeddings yet — that's Phase 9's job (§12.4/[A4])."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO messages (conversation_id, user_id, role, content)
                    VALUES (:conversation_id, :user_id, 'user', :content)
                    """
                ),
                {"conversation_id": conversation_id, "user_id": user_id, "content": user_message},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO messages (conversation_id, user_id, role, content)
                    VALUES (:conversation_id, :user_id, 'assistant', :content)
                    """
                ),
                {"conversation_id": conversation_id, "user_id": user_id, "content": assistant_message},
            )


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """Non-streaming Phase 6 version: resolve user, create/verify the
    conversation, run retrieve -> assemble -> generate, persist both
    messages, return the response as plain JSON.
    """
    if request.conversation_id is None:
        conversation_id, session_state = await _create_conversation(user_id, request.message)
    else:
        conversation_id = request.conversation_id
        await _check_conversation_ownership(user_id, conversation_id)
        session_state = await get_session_state(user_id, conversation_id)

    graph_input = {
        "user_id": user_id,
        "user_input": request.message,
        "conversation_id": conversation_id,
        "session_state": session_state,
        "persona_to_inject": session_state.get("current_persona"),
    }

    # §12.3 step 6 — nodes return PARTIAL state updates, always merge, never
    # reassign. The compiled cliona_graph is not invoked (§4.4); generate_node
    # is called directly here since this phase is non-streaming.
    state: Dict[str, Any] = {}
    state.update(await retrieve_memory_node({**graph_input, **state}))
    state.update(await assemble_prompt_node({**graph_input, **state}))
    state.update(await generate_node({**graph_input, **state}))

    await _persist_messages(conversation_id, user_id, request.message, state["response"])

    return {"response": state["response"], "conversation_id": conversation_id}
