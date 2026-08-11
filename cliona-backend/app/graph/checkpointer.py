from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings


def get_checkpointer():
    """Compiled into cliona_graph but never exercised: /v1/chat calls nodes
    directly and never invokes the compiled graph (§4.4). session_state is
    the real persistence layer (§7).
    """
    raise NotImplementedError("Phase 1")
