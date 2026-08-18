"""Phase 5a standalone check: retrieve_memory_node() against real, non-trivial
fixture data (§4.2).

Not full pytest coverage — calls the node directly with a manually-built
partial state and prints the actual rows returned, so the result is visibly
real (varying similarity scores, an is_active filter that actually excludes
a row), not just "query executed successfully" against an empty table.

Fixture data (inserted separately via Supabase MCP, real embeddings via
classifier.get_embedding — see conversation history, not reproduced here):
  user_id: bc94ec3e-4f8c-4a8a-b498-786333b03b39
  5 messages: 2 about a calculus exam, 2 about a breakup, 1 about hiking
  3 user_facts: likes/hiking (active), studies/calculus (active),
                dislikes/mornings (INACTIVE — must not appear in results)
"""

import asyncio

from app.graph.nodes import retrieve_memory_node

TEST_USER_ID = "bc94ec3e-4f8c-4a8a-b498-786333b03b39"


async def main() -> None:
    state = {
        "user_id": TEST_USER_ID,
        "user_input": "I have another exam coming up and I'm feeling really anxious about it",
    }

    result = await retrieve_memory_node(state)

    assert set(result.keys()) == {"retrieved_memories", "retrieved_facts"}

    print("--- retrieved_memories (top 5 by cosine similarity) ---")
    for m in result["retrieved_memories"]:
        assert set(m.keys()) == {"content", "similarity"}
        print(f"  {m['similarity']:.4f}  {m['content']!r}")

    print("\n--- retrieved_facts (is_active=true only) ---")
    for f in result["retrieved_facts"]:
        assert set(f.keys()) == {"subject", "predicate", "object"}
        print(f"  {f['subject']} {f['predicate']} {f['object']}")

    memories = result["retrieved_memories"]
    assert len(memories) == 5, f"expected all 5 fixture messages (only 5 exist), got {len(memories)}"
    assert memories == sorted(memories, key=lambda m: -m["similarity"]), "not ordered by similarity desc"

    top_content = memories[0]["content"].lower()
    assert "exam" in top_content or "calculus" in top_content, (
        f"expected the exam/calculus message to rank first for an exam-anxiety query, got {top_content!r}"
    )

    facts = result["retrieved_facts"]
    assert len(facts) == 2, f"expected exactly the 2 active facts, got {len(facts)}"
    objects = {f["object"] for f in facts}
    assert objects == {"hiking", "calculus"}, f"expected hiking+calculus, got {objects}"
    assert "mornings" not in objects, "inactive fact (dislikes/mornings) leaked through the is_active filter"

    print("\nPASS: top result is exam/calculus-related, ordering is correct, inactive fact correctly excluded")


def test_retrieve_memory_node_against_fixture_data() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
