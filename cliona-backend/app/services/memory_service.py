"""pgvector retrieval + fact lookup helpers, used by retrieve_memory_node (§4.2)."""

from typing import Any, Dict, List


async def retrieve_semantic_memories(
    user_id: str, query_embedding: Any, limit: int = 5
) -> List[Dict[str, Any]]:
    """Top-N pgvector cosine similarity search over messages, user-scoped
    and cross-conversation (no role filter, no conversation filter).
    """
    raise NotImplementedError("Phase 1")


async def retrieve_active_facts(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Active user_facts rows for a user. Expect zero rows in v1 (§3.5)."""
    raise NotImplementedError("Phase 1")
