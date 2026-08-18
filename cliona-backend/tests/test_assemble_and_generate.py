"""Phase 5b standalone check: assemble_prompt_node() + generate_node() (§4.2/§5).

Prints the FULL assembled prompt string for three persona_to_inject cases —
None, "venting", "deep_emotional" — so the 7-layer hierarchy and the [B1]
"no persona block on None, no casual fallback" rule can be verified by eye,
not just asserted. Then runs generate_node once on the "venting" case's
real assembled prompt against the live OpenRouter model.

Reuses Phase 5a's fixture user_id/conversation_id and does a REAL
retrieve_memory_node() call against the live DB first — retrieved_memories
and retrieved_facts here are the actual Phase 5a rows, not fabricated.
"""

import asyncio

from app.core.database import AsyncSessionLocal  # noqa: F401 (import kept for parity with node modules)
from app.core.llm_factory import LLMFactory
from app.graph.nodes import assemble_prompt_node, generate_node, retrieve_memory_node
from app.main import lifespan, app as fastapi_app

TEST_USER_ID = "bc94ec3e-4f8c-4a8a-b498-786333b03b39"
TEST_CONVERSATION_ID = "c6e2f670-cd88-474b-a97c-b4721fb3267c"

# Matches the real fixture messages inserted in Phase 5a, in chronological
# order — standing in for what session_state.last_3_messages would hold
# after those turns (§7 shape: list of {"role", "content"}, max 6 entries).
LAST_3_MESSAGES = [
    {"role": "user", "content": "I've been really stressed about my calculus exam next week"},
    {"role": "assistant", "content": "Calculus exams are rough. What part is tripping you up, derivatives or integrals?"},
    {"role": "user", "content": "My girlfriend broke up with me last month and I'm still not over it"},
    {"role": "assistant", "content": "Breakups linger. That's not a weakness, that's just how attachment works."},
    {"role": "user", "content": "I love hiking on weekends, it clears my head"},
]


def _print_prompt(label: str, prompt: str) -> None:
    print(f"\n{'=' * 100}")
    print(f"CASE: {label}")
    print("=" * 100)
    print(prompt)
    print("=" * 100)
    print(f"[{len(prompt)} chars total]")


async def main() -> None:
    async with lifespan(fastapi_app):
        base_state = {
            "user_id": TEST_USER_ID,
            "conversation_id": TEST_CONVERSATION_ID,
            "user_input": "I have another exam coming up and I'm feeling really anxious about it",
        }

        # Real retrieval against the live DB (Phase 5a's fixture data) — merged,
        # per §12.3's "nodes return PARTIAL updates, always merge" rule.
        retrieval = await retrieve_memory_node(base_state)
        state = {**base_state, **retrieval}
        state["session_state"] = {"last_3_messages": LAST_3_MESSAGES}

        print("retrieved_memories used below:", len(state["retrieved_memories"]), "rows")
        print("retrieved_facts used below:   ", len(state["retrieved_facts"]), "rows")

        assembled = {}

        # --- Case 1: persona_to_inject = None ---
        state_none = {**state, "persona_to_inject": None}
        result_none = await assemble_prompt_node(state_none)
        assembled["none"] = result_none["final_prompt"]
        _print_prompt("persona_to_inject = None", assembled["none"])

        # Check for the actual injection marker ("--- PERSONA MODE: X ---"), not the loose
        # substring "PERSONA MODE" — that also matches the system prompt's own unrelated
        # "## PERSONA MODES" section header, which is expected, real content.
        assert "--- PERSONA MODE:" not in assembled["none"], "persona block leaked in with persona_to_inject=None"
        assert "--- PERSONA MODE: CASUAL ---" not in assembled["none"], "casual fallback leaked in [B1] violation"
        print("\n[VERIFIED] zero persona block present — no casual fallback, exactly per [B1]")

        # --- Case 2: persona_to_inject = "venting" ---
        state_venting = {**state, "persona_to_inject": "venting"}
        result_venting = await assemble_prompt_node(state_venting)
        assembled["venting"] = result_venting["final_prompt"]
        _print_prompt("persona_to_inject = 'venting'", assembled["venting"])

        assert "--- PERSONA MODE: VENTING ---" in assembled["venting"]
        sys_end = assembled["venting"].index("--- PERSONA MODE: VENTING ---")
        lore_start = assembled["venting"].index("--- LORE ---")
        assert sys_end < lore_start, "persona block not between system prompt and lore"
        for layer in ("--- HARD FACTS ---", "--- PAST MEMORIES ---", "--- RECENT CHAT ---", "User:"):
            assert layer in assembled["venting"], f"missing layer: {layer}"
        assert (
            assembled["venting"].index("--- HARD FACTS ---")
            < assembled["venting"].index("--- PAST MEMORIES ---")
            < assembled["venting"].index("--- RECENT CHAT ---")
            < assembled["venting"].rindex("User:")
        ), "layers 4-7 out of order"
        print("\n[VERIFIED] venting block sits between system prompt and lore; facts->memories->chat->input in order")

        # --- Case 3: persona_to_inject = "deep_emotional" ---
        state_deep = {**state, "persona_to_inject": "deep_emotional"}
        result_deep = await assemble_prompt_node(state_deep)
        assembled["deep_emotional"] = result_deep["final_prompt"]
        _print_prompt("persona_to_inject = 'deep_emotional'", assembled["deep_emotional"])

        assert "--- PERSONA MODE: DEEP_EMOTIONAL ---" in assembled["deep_emotional"]
        sys_end2 = assembled["deep_emotional"].index("--- PERSONA MODE: DEEP_EMOTIONAL ---")
        lore_start2 = assembled["deep_emotional"].index("--- LORE ---")
        assert sys_end2 < lore_start2, "persona block not between system prompt and lore"
        print("\n[VERIFIED] deep_emotional block placed correctly too — not a one-persona fluke")

        # --- generate_node on case 2's real assembled prompt ---
        gen_state = {**state_venting, "final_prompt": assembled["venting"]}
        gen_result = await generate_node(gen_state)

        print("\n" + "=" * 100)
        print("generate_node() response for the 'venting' case:")
        print("=" * 100)
        print(gen_result["response"])
        print("=" * 100)
        assert gen_result["response"].strip(), "empty response from generate_node"

        # Diagnostic: inspect finish_reason/usage directly (not just .content) to see
        # whether the model hit the 1024-token ceiling before producing a final answer.
        llm = LLMFactory.get_llm(streaming=False)
        raw = await llm.ainvoke(assembled["venting"])
        print("\n--- raw response diagnostics ---")
        print("response_metadata:", raw.response_metadata)
        print("usage_metadata:", getattr(raw, "usage_metadata", None))


async def test_assemble_prompt_and_generate_node() -> None:
    await main()


if __name__ == "__main__":
    asyncio.run(main())
