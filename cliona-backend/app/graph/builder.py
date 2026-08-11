"""Compiled graph — retained as dead code, never invoked in the live request
path (CLAUDE.md §4.4, §4.3). Not imported by app.main; nothing in the
streaming path depends on this module. Importing it directly currently
raises NotImplementedError via get_checkpointer() until a later phase wires
up the checkpointer.
"""

from langgraph.graph import StateGraph, END

from app.graph.state import ClionaState
from app.graph.nodes import retrieve_memory_node, assemble_prompt_node, generate_node
from app.graph.checkpointer import get_checkpointer

graph = StateGraph(ClionaState)
graph.add_node("retrieve", retrieve_memory_node)
graph.add_node("assemble", assemble_prompt_node)
graph.add_node("generate", generate_node)

graph.set_entry_point("retrieve")
graph.add_edge("retrieve", "assemble")
graph.add_edge("assemble", "generate")
graph.add_edge("generate", END)

cliona_graph = graph.compile(checkpointer=get_checkpointer())
