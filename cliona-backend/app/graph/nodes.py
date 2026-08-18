from typing import Any, Dict

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.llm_factory import LLMFactory
from app.graph.state import ClionaState
from app.services.classifier import get_embedding

# Populated by main.py lifespan at startup (CLAUDE.md §11.3). Held in RAM.
SYSTEM_PROMPT: str = ""
DYNAMIC_PROMPTS: Dict[str, str] = {}
LORE: Dict[str, Any] = {}

_MEMORIES_QUERY = text(
    """
    SELECT content, 1 - (embedding <=> :emb) AS similarity
    FROM messages
    WHERE user_id = :user_id
    ORDER BY embedding <=> :emb
    LIMIT 5
    """
)

_FACTS_QUERY = text(
    """
    SELECT subject, predicate, object
    FROM user_facts
    WHERE user_id = :user_id AND is_active = true
    LIMIT 20
    """
)


def _to_pgvector_literal(embedding) -> str:
    """pgvector-compatible string form — a raw Python list bound to a text()
    param won't work (§4.2); cast explicitly instead of registering the
    asyncpg adapter, to avoid touching database.py's engine setup.
    """
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


async def retrieve_memory_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: user_id, user_input. Writes: retrieved_memories, retrieved_facts. 2 DB reads."""
    embedding = _to_pgvector_literal(get_embedding(state["user_input"]))

    async with AsyncSessionLocal() as session:
        memories_result = await session.execute(
            _MEMORIES_QUERY, {"emb": embedding, "user_id": state["user_id"]}
        )
        retrieved_memories = [dict(r) for r in memories_result.mappings().all()]

        facts_result = await session.execute(_FACTS_QUERY, {"user_id": state["user_id"]})
        retrieved_facts = [dict(r) for r in facts_result.mappings().all()]

    return {"retrieved_memories": retrieved_memories, "retrieved_facts": retrieved_facts}


async def assemble_prompt_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: persona_to_inject, retrieved_facts, retrieved_memories,
    session_state.last_3_messages, user_input + module globals SYSTEM_PROMPT,
    DYNAMIC_PROMPTS, LORE. Writes: final_prompt. Pure — no side effects.
    """
    # 1. System prompt
    final_prompt = SYSTEM_PROMPT + "\n\n"

    # 2. Persona — injected ONLY when one is pending. No casual fallback. [B1]
    persona_key = state.get("persona_to_inject")
    if persona_key and persona_key in DYNAMIC_PROMPTS:
        final_prompt += f"--- PERSONA MODE: {persona_key.upper()} ---\n"
        final_prompt += DYNAMIC_PROMPTS[persona_key] + "\n\n"

    # 3. Lore
    final_prompt += f"--- LORE ---\n{LORE}\n\n"

    # 4. Hard facts
    facts_text = "--- HARD FACTS ---\n"
    for fact in state["retrieved_facts"]:
        facts_text += f"- {fact['subject']} {fact['predicate']} {fact['object']}\n"
    final_prompt += facts_text + "\n"

    # 5. Semantic memories
    memories_text = "--- PAST MEMORIES ---\n"
    for mem in state["retrieved_memories"]:
        memories_text += f"- {mem['content']}\n"
    final_prompt += memories_text + "\n"

    # 6. Short-term context
    context_text = "--- RECENT CHAT ---\n"
    for msg in state["session_state"].get("last_3_messages", []):
        context_text += f"{msg['role']}: {msg['content']}\n"
    final_prompt += context_text + "\n"

    # 7. Current input
    final_prompt += f"User: {state['user_input']}\n\nCliona:"

    return {"final_prompt": final_prompt}


async def generate_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: final_prompt. Writes: response. LLM call (non-streaming) —
    unused in the live request path (CLAUDE.md §4.4).
    """
    llm = LLMFactory.get_llm(streaming=False)
    response = await llm.ainvoke(state["final_prompt"])
    return {"response": response.content}
