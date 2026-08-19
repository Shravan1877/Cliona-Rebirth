"""[B14] session_state CRUD. One row per conversation, keyed by
conversation_id (§3.1, §7). Both functions take both ids: conversation_id
selects the row, user_id is the ownership guard on the WHERE clause.
"""

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def get_session_state(user_id: str, conversation_id: str) -> dict:
    """A missing row is an error condition, not a create trigger — there is
    no lazy creation. The row is created at conversation creation time only.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT conversation_id, user_id, turn_count, current_persona,
                       pending_persona, last_3_messages, updated_at
                FROM session_state
                WHERE conversation_id = :conversation_id AND user_id = :user_id
                """
            ),
            {"conversation_id": conversation_id, "user_id": user_id},
        )
        row = result.mappings().first()

    if row is None:
        raise LookupError(
            f"no session_state row for conversation_id={conversation_id!r}, user_id={user_id!r} "
            "— every conversation gets one at creation time (§7), this is an invariant violation"
        )

    state = dict(row)
    state["last_3_messages"] = state["last_3_messages"] or []
    return state


async def update_session_state(user_id: str, conversation_id: str, updates: dict) -> None:
    """Full pending_persona/turn_count read-write lifecycle — Phase 8 (§6.3/§7)."""
    raise NotImplementedError("Phase 8")
