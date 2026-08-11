"""[B14] session_state CRUD. One row per conversation, keyed by
conversation_id (§3.1, §7). Both functions take both ids: conversation_id
selects the row, user_id is the ownership guard on the WHERE clause.
"""


async def get_session_state(user_id: str, conversation_id: str) -> dict:
    """A missing row is an error condition, not a create trigger — there is
    no lazy creation. The row is created at conversation creation time only.
    """
    raise NotImplementedError("Phase 1")


async def update_session_state(user_id: str, conversation_id: str, updates: dict) -> None:
    raise NotImplementedError("Phase 1")
