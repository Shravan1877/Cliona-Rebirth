from typing import Any, Dict

from app.graph.state import ClionaState

# Populated by main.py lifespan at startup (CLAUDE.md §11.3). Held in RAM.
SYSTEM_PROMPT: str = ""
DYNAMIC_PROMPTS: Dict[str, str] = {}
LORE: Dict[str, Any] = {}


async def retrieve_memory_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: user_id, user_input. Writes: retrieved_memories, retrieved_facts. 2 DB reads."""
    raise NotImplementedError("Phase 1")


async def assemble_prompt_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: persona_to_inject, retrieved_facts, retrieved_memories,
    session_state.last_3_messages, user_input + module globals SYSTEM_PROMPT,
    DYNAMIC_PROMPTS, LORE. Writes: final_prompt. Pure — no side effects.
    """
    raise NotImplementedError("Phase 1")


async def generate_node(state: ClionaState) -> Dict[str, Any]:
    """Reads: final_prompt. Writes: response. LLM call (non-streaming) —
    unused in the live request path (CLAUDE.md §4.4).
    """
    raise NotImplementedError("Phase 1")
