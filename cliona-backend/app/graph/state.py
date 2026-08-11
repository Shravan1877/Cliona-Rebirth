from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict


class ClionaState(TypedDict):
    user_id: str
    user_input: str
    conversation_id: str
    session_state: Dict[str, Any]
    retrieved_memories: List[Dict[str, Any]]
    retrieved_facts: List[Dict[str, Any]]
    lore: Dict[str, Any]
    persona_to_inject: Optional[str]  # One of the 8 keys, or None
    final_prompt: str
    response: str
    error: Optional[str]
