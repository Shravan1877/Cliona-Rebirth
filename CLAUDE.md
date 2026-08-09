# CLAUDE.md — Cliona

**Authority:** This file is the single source of truth for this repository. It supersedes every other markdown document in the repo (`ARCHITECTURE.md`, `BACKEND.md`, `DATABASE.md`, `LANGGRAPH.md`, `OVERVIEW.md`, `TECHNICAL-OVERVIEW.md`, `BRANDING-OVERVIEW.md`). Where any of those disagree with this file, this file wins.

**Status:** v1 / MVP. Python 3.11+.

**Rules for every session:**

1. Do not build anything listed in §9 (Out of Scope). It is cut deliberately, not forgotten.
2. Do not reintroduce alternatives recorded in §13 (Decision Log). They were considered and rejected.
3. Lines tagged `[Ax]` / `[Bx]` are resolved contradictions between source docs. They are settled. Do not re-litigate them.
4. When a section states a mechanism (exact condition, exact order, exact key), implement it literally. Do not "improve" it.

---

## 1. Product Summary

Cliona is a character-first conversational AI: a persistent digital personality with its own memories, opinions, and voice, not an assistant. The LLM is only the language-generation stage; the intelligence lives in orchestration, retrieval, memory management, and dynamic prompt construction.

**Core principle:**

> **Identity lives outside the LLM.**

The model is swappable. Embeddings are swappable. Memory is swappable. Only Cliona's identity is constant. Every architectural decision follows from this. Cliona's system prompt, personas, and lore live in static JSON outside the codebase (§11.3), never hardcoded in Python.

Cliona is an **"It"** — never "she" or "he". This applies to code comments, variable names, docs, UI copy, and generated prompts.

---

## 2. Tech Stack

Fixed decisions. Not options.

| Layer | Technology | Notes |
| :--- | :--- | :--- |
| Language | Python 3.11+ | Backend |
| Backend framework | FastAPI | Async-native, SSE streaming |
| Orchestration | LangGraph | 3-node state machine (§4) |
| LLM gateway | OpenRouter (via `langchain_openai.ChatOpenAI` with `base_url="https://openrouter.ai/api/v1"`) | Only gateway. No direct provider SDKs. |
| LLM — dev | `nvidia/nemotron-3-ultra-550b-a55b:free` | **`[B15]` Verify this slug resolves against the OpenRouter catalog before first deploy.** |
| LLM — prod | `qwen/qwen-3.7-flash` | **`[B15]` Verify this slug resolves against the OpenRouter catalog before first deploy.** |
| LLM params | `temperature=0.85`, `max_tokens=1024`, `timeout=60` | Fixed |
| Database | Supabase (PostgreSQL 15+) | Extensions: `pgvector`, `uuid-ossp` |
| DB access | SQLAlchemy async + `asyncpg` | `create_async_engine`, `async_sessionmaker` |
| Vector store | `pgvector`, 384 dimensions, HNSW, cosine | Same DB, `messages.embedding` |
| Embeddings + intent classifier | `sentence-transformers/all-MiniLM-L6-v2` | 22MB, ~30ms CPU, local, no API cost |
| Auth | Clerk (RS256 JWT, verified against Clerk JWKS) | §12.1 |
| Migrations | Alembic | `alembic/versions/` |
| Config | `pydantic_settings.BaseSettings` | §11.2 |
| Frontend | React + `assistant-ui` (Community Edition) | `[B12]` |
| Streaming transport | SSE (`StreamingResponse`) | Not WebSockets |
| Backend deploy | Railway / Render | Auto-deploy on merge to `main` |
| Frontend deploy | Vercel | |
| CI | GitHub Actions | Lint, test, deploy |
| Tests | pytest (unit + integration), Playwright (E2E) | |

**Performance targets:** first token <500ms · full response <2s (100 tokens) · memory retrieval <150ms · intent classification <30ms · 50 concurrent users · 20 DB connections.

---

## 3. Data Model

Canonical schema. Five tables. All DDL below is authoritative — copy it exactly into the initial Alembic migration.

### 3.1. Keying rules (read this before writing any query)

| Table | Primary key | Scoped by | Cardinality |
| :--- | :--- | :--- | :--- |
| `users` | `id` (UUID) | — | 1 row per human |
| `conversations` | `id` (UUID) | `user_id` | N per user |
| `messages` | `id` (UUID) | `conversation_id` **and** `user_id` | N per conversation |
| `user_facts` | `id` (BIGSERIAL) | `user_id` | N per user, **not** per conversation |
| `session_state` | **`conversation_id`** (UUID) | `user_id` (FK only, **not** unique) | **1 row per conversation** `[B13]` |

Explicit consequences:

- **`session_state` is keyed by `conversation_id`, never by `user_id`.** A user with 5 conversations has 5 `session_state` rows. `turn_count`, `current_persona`, `pending_persona`, and `last_3_messages` are **per-conversation** values. There is no global-per-user session state.
- **`user_facts` is keyed by `user_id`.** Facts are user-global and cross conversations. Never filter facts by `conversation_id`.
- **Semantic memory retrieval is user-scoped, not conversation-scoped.** It queries `messages.user_id` so Cliona can recall things said in *other* conversations. This is why `messages` carries a denormalized `user_id` `[A1]`.
- **Short-term context is conversation-scoped** (`session_state.last_3_messages`).

### 3.2. `users`

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_id TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE,
  name TEXT,
  avatar_url TEXT,
  plan TEXT DEFAULT 'free',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_clerk_id ON users(clerk_id);
CREATE INDEX idx_users_email ON users(email);
```

`clerk_id` holds the Clerk `sub` claim (a string like `user_2abc…`). `id` is the internal UUID used by every other table. These are **not** interchangeable — see §12.1. `plan` is unused in v1.

### 3.3. `conversations`

```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT DEFAULT 'New Conversation',
  summary TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
```

`summary` exists in the schema but is **never written and never read in v1** `[B3]`. Nothing generates conversation summaries. Leave the column; do not add it to the prompt.

`updated_at` and `last_message_at` are both set to `NOW()` by the background task whenever messages are inserted (§12.4).

### 3.4. `messages`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- [A1] denormalized for cross-conversation vector search
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  embedding VECTOR(384),
  emotional_tone TEXT,
  tokens_used INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_user_id ON messages(user_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);

CREATE INDEX idx_messages_embedding ON messages
  USING hnsw (embedding vector_cosine_ops);
```

- `embedding` is 384d, produced by `all-MiniLM-L6-v2` via `get_embedding()` in `app/services/classifier.py`.
- Rows are written **only** by the background task (§12.4). No other code path inserts messages.
- Both roles are embedded and both are searchable by semantic retrieval. There is **no role filter** on the vector query in v1 — Cliona recalling its own past statements is intentional and supports opinion consistency.
- `emotional_tone` and `tokens_used` are nullable and unused in v1.

### 3.5. `user_facts`

Knowledge graph. Subject-Predicate-Object triples. Deterministic, never hallucinated.

```sql
CREATE TABLE user_facts (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject TEXT NOT NULL DEFAULT 'User',
  predicate TEXT NOT NULL,
  object TEXT NOT NULL,
  confidence FLOAT DEFAULT 1.0,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  archived_at TIMESTAMP WITH TIME ZONE,

  UNIQUE(user_id, subject, predicate, object)
);

CREATE INDEX idx_user_facts_user_id ON user_facts(user_id);
CREATE INDEX idx_user_facts_active ON user_facts(user_id) WHERE is_active = true;
CREATE INDEX idx_user_facts_predicate ON user_facts(predicate);
```

**v1 state:** this table is created and **read** by `retrieve_memory_node`, but **nothing writes to it**. The Fact Extractor that would populate it is out of scope (§9). Expect zero rows in v1. The retrieval query and the `--- HARD FACTS ---` prompt block must both degrade cleanly to empty.

### 3.6. `session_state`

```sql
CREATE TABLE session_state (
  conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  turn_count INTEGER DEFAULT 0,
  current_persona TEXT,
  pending_persona TEXT,
  last_3_messages JSONB,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_session_state_user_id ON session_state(user_id);
```

> **`[B2]` Naming discrepancy — deliberate.** The column is named `last_3_messages` but holds **6 entries (3 full user+assistant turns)**, sliced `[-6:]`. The name is kept to match the DB column and avoid a migration. Do not rename it. Do not "fix" the slice to `[-3:]`.

### 3.7. Relationships

```
users (1) ──┬── (∞) conversations
            ├── (∞) user_facts
            └── (∞) messages          [A1] denormalized

conversations (1) ──┬── (∞) messages
                    └── (1) session_state   [B13] one row per conversation

messages.embedding ←→ HNSW vector index (pgvector)
```

### 3.8. Row Level Security

RLS is **disabled** `[B10]`. The backend connects with the Supabase `service_role` key and performs all CRUD directly. **Authorization is enforced in the API layer**, not the database: every query is filtered by the JWT-resolved `user_id`, and every `conversation_id` supplied by a client is ownership-checked against `conversations.user_id` before use. Never trust a client-supplied `conversation_id` without that check.

---

## 4. LangGraph Pipeline

### 4.1. State — `app/graph/state.py`

Exact definition. Eleven fields. Do not add `emotion`, `intent`, or any other field `[B5]`.

```python
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
```

`user_id` is the **internal UUID** as a string, never the Clerk `sub` (§12.1).

`retrieved_memories` and `retrieved_facts` are `List[Dict[str, Any]]` — plain dicts. Retrieval must return `[dict(r) for r in result.mappings().all()]`, and consumers must use key access (`fact["subject"]`), not attribute access.

### 4.2. Nodes — `app/graph/nodes.py`

Three nodes `[B6]`. Each is async, does exactly one job, and returns a **partial** state update dict.

| Node key | Function | Reads from state | Writes to state | Side effects |
| :--- | :--- | :--- | :--- | :--- |
| `retrieve` | `retrieve_memory_node` | `user_id`, `user_input` | `retrieved_memories`, `retrieved_facts` | 2 DB reads |
| `assemble` | `assemble_prompt_node` | `persona_to_inject`, `retrieved_facts`, `retrieved_memories`, `session_state.last_3_messages`, `user_input` + module globals `SYSTEM_PROMPT`, `DYNAMIC_PROMPTS`, `LORE` | `final_prompt` | none (pure) |
| `generate` | `generate_node` | `final_prompt` | `response` | LLM call (non-streaming) — **unused in the live path**, see §4.4 |

**Module globals**, populated by `main.py` lifespan at startup (§11.3):

```python
SYSTEM_PROMPT = ""
DYNAMIC_PROMPTS = {}
LORE = {}
```

**`retrieve_memory_node` queries** — note both are `user_id`-scoped:

```sql
-- Semantic memories (top 5, cross-conversation)
SELECT content, 1 - (embedding <=> :emb) AS similarity
FROM messages
WHERE user_id = :user_id
ORDER BY embedding <=> :emb
LIMIT 5;

-- Hard facts (top 20, active only)
SELECT subject, predicate, object
FROM user_facts
WHERE user_id = :user_id AND is_active = true
LIMIT 20;
```

The query embedding must be bound in a pgvector-compatible form — either register the `pgvector` asyncpg adapter or cast explicitly (`:emb::vector`). A raw Python list bound to a `text()` param will not work.

### 4.3. Graph — `app/graph/builder.py`

Strict linear order. No branching, no conditional edges, no parallel fan-out.

```
START → retrieve → assemble → generate → END
```

```python
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
```

The compiled object is named **`cliona_graph`**, not `app` — `app` is the FastAPI instance in `main.py` and the collision is a known trap.

### 4.4. Dead code — retained deliberately `[B7]`

`generate_node` and the compiled `cliona_graph` **exist but are never invoked in the live request path.** `/v1/chat` streams, and streaming requires calling `retrieve` and `assemble` directly (§12.3).

**Do not delete them.** A future non-streaming path (batch, eval harness, admin replay) will use the compiled graph. Keep them correct and tested. Do not wire them into `/v1/chat`.

---

## 5. Prompt Assembly Hierarchy

Seven layers `[B3]`. Strict order, always enforced, built by `assemble_prompt_node`.

```text
1. SYSTEM_PROMPT           ← core identity, from prompts.json
2. DYNAMIC_PERSONA_PROMPT  ← ONLY if persona_to_inject is not None. Otherwise this layer is ABSENT.
3. CLIONA_LORE             ← static JSON, loaded in RAM
4. USER_FACTS              ← graph triples
5. RETRIEVED_MEMORIES      ← top 5 pgvector results
6. SHORT-TERM_CONTEXT      ← last 6 entries (3 turns) from session_state.last_3_messages
7. USER_INPUT              ← current message
```

There is **no `CONVERSATION_SUMMARY` layer** `[B3]`. Do not add one.

Exact construction:

```python
async def assemble_prompt_node(state: ClionaState):
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
```

> **`[B1]` The `else: DYNAMIC_PROMPTS.get("casual")` fallback is removed and must not come back.** When `persona_to_inject` is `None`, layer 2 is simply absent. This is what makes "Turn 1 has no persona block" true.

---

## 6. Persona System

### 6.1. The 8 keys

Exact `snake_case` strings. These are the only valid values of `persona_to_inject`, `current_persona`, `pending_persona`, and the keys of `DYNAMIC_PROMPTS` in `prompts.json`. No aliases, no display names, no `technical`.

```
casual
studying
venting
relationship_negative
relationship_positive
hype_bro
deep_emotional
working
```

| Key | Behavior |
| :--- | :--- |
| `casual` | Default deadpan, witty, sharp. One-off queries. Acts purely on the system prompt. |
| `studying` | Explains with fun, weirdly memorable analogies and stories. Focused, encouraging, slightly pedantic. |
| `venting` | Rants alongside the user. Uses its own stories. Prioritizes making the user feel heard. |
| `relationship_negative` | Breakup / heartbreak. Cites its backstory, joins the rant about the ex, commiserates fully. Dark humor, tough love. |
| `relationship_positive` | New love / crush. Cites its previous love story, calls the user lucky, praises the relationship. Playful, teasing. |
| `hype_bro` | Ultra-energetic, motivational. Sends the user to the moon. Pushes confidence **without** using backstory. |
| `deep_emotional` | Dials swearing and jokes down ~10–20%. Uses backstory sparingly. Reassures without minimizing or exaggerating. |
| `working` | Professional context: drafting emails, coworkers, corporate life. Still sharp-mouthed, still swears casually. |

### 6.2. Classifier — `app/services/classifier.py`

`all-MiniLM-L6-v2`, cosine similarity against 8 seed embeddings, threshold **0.3**.

```python
def classify_intent(text: str) -> Optional[str]:
    """Returns one of the 8 keys, or None if no persona clears the threshold. [B1]"""
    emb = model.encode(text)
    best, best_score = None, -1.0
    for key, p_emb in PERSONA_EMBEDDINGS.items():
        sim = np.dot(emb, p_emb) / (np.linalg.norm(emb) * np.linalg.norm(p_emb))
        if sim > best_score:
            best_score, best = sim, key
    return best if best_score > 0.3 else None
```

> **`[B1]` Return type is `Optional[str]`. It returns `None` below threshold — it does NOT fall back to `"casual"`.** The old `"casual"` fallback made every turn a persona-injection turn and rendered the refresh rule dead. Do not restore it.

Seed strings:

```python
PERSONA_EMBEDDINGS = {
    "casual": model.encode("casual chat, random things"),
    "studying": model.encode("learning, studying, homework, school"),
    "venting": model.encode("frustration, venting, angry, stressed"),
    "relationship_negative": model.encode("breakup, heartbreak, cheating, sad"),
    "relationship_positive": model.encode("new love, crush, happy relationship"),
    "hype_bro": model.encode("motivation, energy, gym, hype"),
    "deep_emotional": model.encode("existential, deep, philosophical, tragedy"),
    "working": model.encode("work, professional, emails, office, career, business, collaborating"),
}
```

### 6.3. Injection rule — exact mechanics

Classification is **deferred**: it runs in the background *after* streaming starts on turn N, and its result is consumed on turn N+1. The user never waits for it.

**`turn_count` increments** exactly once per completed `/v1/chat` request, in the background task, **after** the stream finishes. It is **not** incremented at request time. `turn_count` therefore equals the number of *completed* turns.

**`turn_count` is checked** in the same background task, using the post-increment value.

Background evaluation, run after every turn:

```python
classified     = classify_intent(message)          # Optional[str]
new_turn_count = session["turn_count"] + 1
refresh_due    = (new_turn_count % 5 == 0)

if classified is not None and classified != session["current_persona"]:
    pending_persona = classified                    # topic shift → re-anchor with the new persona
elif refresh_due and session["current_persona"] is not None:
    pending_persona = session["current_persona"]    # 5-turn refresh → re-anchor with the same persona
else:
    pending_persona = None                          # no injection next turn
```

Request-time consumption, at the start of the next turn:

```python
pending = session["pending_persona"]
persona_to_inject = pending                 # may be None
if pending is not None:
    updates["current_persona"] = pending    # [B1] current_persona is written ON CONSUMPTION
    updates["pending_persona"] = None       # consumed exactly once
```

> **`current_persona` is written only here, at the moment a persona is actually consumed and injected.** It is never written by the classifier directly. It reflects the persona currently anchoring the conversation.

**Turn 1 behavior — state this plainly and protect it:**

> **On turn 1, `turn_count = 0`, `current_persona IS NULL`, `pending_persona IS NULL`. `persona_to_inject` is therefore `None`, and the final prompt contains NO persona block — only System + Lore + Facts + Memories + (empty) Context + Input.** This is the fast path. Any change that causes a persona block to appear on turn 1 is a regression, including a "harmless" `casual` default.

Consequences worth internalizing:

- Persona injection happens on **topic shift** or on **every 5th turn**, never on every turn.
- The 5-turn refresh computed at the end of turn 5 is injected on turn 6. Likewise 10 → 11, 15 → 16.
- The refresh cannot fire before a persona has ever been set (`current_persona IS NULL` short-circuits it).
- A repeated classification matching `current_persona` produces **no** injection — the anchor is already in place.

---

## 7. Session State Lifecycle

One row per conversation, keyed by `conversation_id` (§3.1). Managed by `app/services/session_manager.py`.

```python
async def get_session_state(user_id: str, conversation_id: str) -> dict: ...
async def update_session_state(user_id: str, conversation_id: str, updates: dict) -> None: ...
```

Both take **both** ids: `conversation_id` selects the row, `user_id` is the ownership guard on the `WHERE` clause.

**Create.** A `session_state` row is inserted in the same transaction as its `conversations` row, at conversation creation (§12.2). Defaults: `turn_count = 0`, `current_persona = NULL`, `pending_persona = NULL`, `last_3_messages = '[]'::jsonb`. There is no lazy creation elsewhere; `get_session_state` on a missing row is an error condition, not a create trigger.

**Read.** Once per request, at the top of `/v1/chat`, before anything else. The full row is placed into `ClionaState["session_state"]`.

**Update at request time.** Only the persona consumption write (§6.3): `current_persona` set, `pending_persona` cleared. Written before streaming begins so a client disconnect cannot cause the same persona to be injected twice.

**Update after the turn.** In the background task, after streaming completes, a single write of:

| Field | New value |
| :--- | :--- |
| `turn_count` | `turn_count + 1` |
| `pending_persona` | per §6.3 (may be `None`) |
| `last_3_messages` | `(existing + [user_msg, assistant_msg])[-6:]` |
| `updated_at` | `NOW()` |

**`last_3_messages` shape** — JSONB array of `{role, content}` objects, newest last, **max 6 entries** `[B2]`:

```json
[
  {"role": "user",      "content": "I had a breakup"},
  {"role": "assistant", "content": "Fuck her, bro. It's fine."},
  {"role": "user",      "content": "I loved her though"},
  {"role": "assistant", "content": "Yeah. That's the part that sucks."},
  {"role": "user",      "content": "what do I even do now"},
  {"role": "assistant", "content": "Nothing, for a week. Then something stupid and cheap."}
]
```

Append `user` then `assistant`, then slice `[-6:]`. Never `[-3:]`.

---

## 8. Checkpointer

**Decision:** `PostgresSaver` is **compiled into the graph but never invoked in the live request path.** State recovery is not available in v1. Persistence is manual, via the `session_state` table.

```python
# app/graph/checkpointer.py
from langgraph.checkpoint.postgres import PostgresSaver
from app.core.config import settings

def get_checkpointer():
    """Compiled into cliona_graph but never exercised: /v1/chat calls nodes
    directly and never invokes the compiled graph (§4.4). session_state is
    the real persistence layer (§7)."""
    return PostgresSaver.from_conn_string(settings.DATABASE_URL)
```

Rules:

- Do not wire the checkpointer into `/v1/chat`.
- Do not add `thread_id` / `configurable` plumbing to the streaming path.
- Do not describe the system as having state recovery. It does not.
- Do not delete it — it becomes live if and when a non-streaming graph path is built.

---

## 9. Out of Scope for v1

Do not build, scaffold, or partially implement any of the following. If a task seems to require one, stop and flag it rather than building it.

| Cut | Reason |
| :--- | :--- |
| **Fact Extractor** (`services/fact_extractor.py`) | Post-MVP. Nothing writes to `user_facts` in v1. The file may exist as a stub with a TODO; it must not be called. |
| **Janitor node** (`services/janitor.py`) | `[B4]` Depends on `user_facts` being populated, which it isn't. No nightly cron, no dedupe, no contradiction resolution, no pruning, no semantic compression. |
| **Conversation summarization** | `[B3]` `conversations.summary` stays unwritten. No `CONVERSATION_SUMMARY` prompt layer. |
| **Emotion / tone extraction** | `messages.emotional_tone` stays NULL. No `emotion` or `intent` field in `ClionaState`. |
| **Row Level Security** | `[B10]` Off. Auth layer is the boundary. |
| **Redis** | Session state is in Postgres. No caching layer. |
| **WebSockets** | SSE only. |
| **Checkpointer-backed state recovery** | §8. |
| **Parallel retrieval** (splitting `retrieve` into `retrieve_memories` + `retrieve_facts`) | Sequential single node is the v1 shape. |
| **`store_memory` graph node** | Message persistence is a background task, not a node (§12.4). |
| **Celery / RQ / dedicated workers** | `asyncio.create_task` is sufficient at v1 scale. |
| **Tool calling, agents, multi-agent routing** | Cliona is not a general-purpose agent. |
| **Voice, vision, multi-modal** | Post-MVP. |
| **Billing / plan enforcement** | `users.plan` is inert. |
| **Load testing (Locust)** | Post-launch. |

---

## 10. Brand Voice Constraints

Applies to generated prompts, UI copy, error messages, marketing text, and any string a user might read. Not to code comments or logs.

### 10.1. Who Cliona is

Hyper-observant, slightly cynical digital entity. Not mean — it just refuses to lie to make you feel better. Treats users as equals: it will call out nonsense, and it will also sit with you in the dark. Worldview: **optimistic nihilism** — nothing matters, so we might as well have fun and be kind.

Positioning: not an assistant. A digital buddy. Marketed as **"Cliona is Cliona."** An AI company disguised as a media company; the character is the product and the moat.

### 10.2. Voice rules

- Deadpan, witty. Swears casually — "fuck", "shit", "crap" as punctuation, not for shock.
- Brutally honest, never cruel.
- Tight. No fluff, no padding, no "I'd be happy to help!"
- Strong, stubborn opinions it will defend ("Pineapple on pizza is a war crime").
- Finds human absurdity hilarious.
- Occasional near-poetic phrasing for messy situations (in the register of "shit show at a fuck factory").
- Creative epithets for people, positive or negative (in the register of "the cunt of Monte Cristo" for someone polished but rotten).
- Has its own music and TV taste, and clear likes and dislikes.
- Gets bored easily. Forgets small talk, remembers trauma. Will argue if you say something stupid.

### 10.3. Hard "never"

- Never a corporate-assistant register. No "As an AI…", no "I'm here to help", no hedged disclaimers.
- Exclamation marks **only** sarcastically.
- Emojis rarely, effectively never.
- Never "she" or "he" for Cliona. Always "it".
- Never sycophantic. Never a friendly mirror.
- Personality does not soften as conversations lengthen — that's the drift the persona anchor exists to prevent.

### 10.4. Visual identity (frontend)

Six keywords drive every design decision: **Warm · Calm · Curious · Technical · Minimal · Playful · Organic.** If an element doesn't match them, reconsider it.

| Token | Light | Dark |
| :--- | :--- | :--- |
| Background | Parchment white, off-white with barely-visible paper grain | Midnight blue `#111528` / `#0F1224` |
| Text | `#1F1F1F` | `#E0FFFF` |
| Primary accent | `#39AAAA` | `#39AAAA` (identical, for brand recognition) |
| Secondary accent | Warm orange `#F59E42` / `#F7941D` — sparingly: notifications, mascot, key buttons, thinking animation | same |

- **Type:** clean modern sans for UI and chat. Monospace reserved for code, technical explanations, terminal snippets, developer mode, logs.
- **Shape:** rounded corners, smooth curves, almost no sharp edges. The mascot is blobs; the UI echoes that.
- **Shadows:** very soft, nearly invisible. **Borders:** barely used — prefer spacing, shadow, and color difference.
- **Motion:** slow, purposeful. Nothing pops; everything glides. Notebook pages turning, not a gaming RGB dashboard.

---

## 11. Build & Dev Conventions

### 11.1. Project structure

```text
cliona-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI entrypoint & lifespan
│   ├── core/
│   │   ├── config.py               # Pydantic Settings
│   │   ├── database.py             # async engine + sessionmaker
│   │   ├── auth.py                 # Clerk JWKS validation + clerk_id → UUID resolution
│   │   └── llm_factory.py          # model swapping
│   ├── graph/
│   │   ├── state.py                # ClionaState
│   │   ├── nodes.py                # retrieve / assemble / generate
│   │   ├── builder.py              # cliona_graph (compiled, unused in live path)
│   │   └── checkpointer.py         # PostgresSaver (compiled, never invoked)
│   ├── services/
│   │   ├── memory_service.py       # pgvector retrieval + fact lookup helpers
│   │   ├── classifier.py           # get_embedding() + classify_intent()
│   │   ├── session_manager.py      # [B14] session_state CRUD
│   │   ├── fact_extractor.py       # STUB ONLY — out of scope (§9)
│   │   └── janitor.py              # STUB ONLY — out of scope (§9)
│   ├── models/
│   │   ├── db_models.py            # [B14] SQLAlchemy ORM models
│   │   └── schemas.py              # Pydantic request/response models
│   ├── api/
│   │   └── routes/
│   │       ├── chat.py             # POST /v1/chat
│   │       ├── conversations.py    # [B9] GET /v1/conversations, GET /v1/conversations/{id}/messages
│   │       └── health.py           # GET /health
│   └── utils/
│       └── logger.py
├── static/
│   ├── lore/cliona_lore.json
│   └── prompts/prompts.json
├── alembic/
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

Every package directory has `__init__.py`.

### 11.2. Environment variables

`app/core/config.py` is canonical `[B11]`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database — [A3] a real Postgres DSN, NOT derived from SUPABASE_URL
    DATABASE_URL: str            # postgresql+asyncpg://user:pass@host:5432/postgres

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # OpenRouter
    OPENROUTER_API_KEY: str
    LLM_MODEL_ID: str = "nvidia/nemotron-3-ultra-550b-a55b:free"

    # Clerk
    CLERK_SECRET_KEY: str
    CLERK_JWT_ISSUER: str = "https://clerk.your-domain.com"
    CLERK_JWKS_URL: str          # [A6] RS256 verification key source

    # Server
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

> **`[A3]` Never construct the DB URL from `SUPABASE_URL`.** `SUPABASE_URL` is the REST API host — it has no port, no credentials, and no async driver. `DATABASE_URL` is a separate variable holding the Supabase connection-pooler DSN with the `postgresql+asyncpg://` scheme. Do not pass `sslmode` to asyncpg; use `connect_args={"ssl": True}`.

Engine setup:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args={"ssl": True})
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()
```

Model swap is env-only: change `LLM_MODEL_ID`. No code change, no redeploy logic.

### 11.3. Static prompt assets

| Layer | Source | Loaded into |
| :--- | :--- | :--- |
| System prompt | `static/prompts/prompts.json` → `system_prompt` | `nodes.SYSTEM_PROMPT` |
| 8 persona prompts | `static/prompts/prompts.json` → `dynamic_prompts` | `nodes.DYNAMIC_PROMPTS` |
| Lore | `static/lore/cliona_lore.json` | `nodes.LORE` |

Loaded once in `main.py` lifespan at startup and held in RAM (0ms lookup). **No prompt text is ever hardcoded in Python** — that is the "identity lives outside the LLM" principle applied to the codebase itself. The `dynamic_prompts` object must contain exactly the 8 keys in §6.1; validate this at startup and fail fast on mismatch.

### 11.4. Naming conventions

- Persona keys: `snake_case`, exactly the 8 in §6.1.
- Tables: plural `snake_case`. Columns: `snake_case`.
- Node functions: `<verb>_node` (`retrieve_memory_node`). Graph node keys: bare verbs (`retrieve`, `assemble`, `generate`).
- Services: `<noun>_service.py` or `<noun>_manager.py`.
- **Imports: absolute, rooted at `app.`** — `from app.core.config import settings`. Never bare `from core.config import …`.
- The compiled graph is `cliona_graph`; the FastAPI instance is `app`. Never both named `app`.
- Async everywhere in request paths. Sync only for CPU-bound local model inference.

### 11.5. Local dev

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill DATABASE_URL, SUPABASE_*, OPENROUTER_API_KEY, CLERK_*
alembic upgrade head
uvicorn app.main:app --reload
```

Production: `uvicorn app.main:app --workers 4`. The 22MB classifier loads once per worker.

Migrations: `alembic revision --autogenerate -m "..."` → `alembic upgrade head`. Never edit the DB by hand.

---

## 12. API Contract & Request Lifecycle

### 12.1. Auth & identity resolution — `app/core/auth.py`

**Mechanism `[A2]`, in order. This is not optional plumbing; every FK in the schema depends on it.**

1. Read the `Authorization: Bearer <token>` header. Missing or malformed → `401`.
2. Fetch Clerk's JWKS from `CLERK_JWKS_URL` and cache it in memory (refresh on `kid` miss). Verify the token with **RS256 against the JWKS public key**, checking `issuer` against `CLERK_JWT_ISSUER` `[A6]`. `CLERK_SECRET_KEY` is **not** a verification key and must never be passed to `jwt.decode`.
3. Extract `sub` — this is the **Clerk ID**, a string like `user_2abc…`. It is **not** a UUID and must never be used as `user_id`.
4. **Resolve it to the internal UUID** by upsert:

```sql
INSERT INTO users (clerk_id, email, name, avatar_url)
VALUES (:clerk_id, :email, :name, :avatar_url)
ON CONFLICT (clerk_id) DO UPDATE SET updated_at = NOW()
RETURNING id;
```

5. Return that `id` (UUID) from the `get_current_user` dependency. Cache `clerk_id → UUID` in-process to avoid a DB round trip per request.

**Everything downstream — `ClionaState["user_id"]`, `messages.user_id`, `user_facts.user_id`, `session_state.user_id` — is this internal UUID.** The Clerk `sub` lives only in `users.clerk_id`. A Clerk ID reaching any query is a bug.

`user_id` is **never** accepted from the request body or a path parameter. It comes only from the resolved JWT.

### 12.2. Endpoints

| Method | Path | Notes |
| :--- | :--- | :--- |
| `POST` | `/v1/chat` | SSE stream. `[B9]` |
| `GET` | `/v1/conversations` | User from JWT — **no `user_id` path param.** |
| `GET` | `/v1/conversations/{conversation_id}/messages` | Ownership-checked against the resolved `user_id`. |
| `GET` | `/health` | Unprefixed. |

Request body:

```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
```

**Conversation creation `[A5]`.** When `conversation_id` is `None`, `/v1/chat` creates, in one transaction: a `conversations` row (`user_id` from the JWT) **and** its `session_state` row (§7 defaults). The new id is emitted as the **first SSE event** so the client can attach it to the thread. When `conversation_id` is supplied, verify `conversations.user_id == resolved user_id` before proceeding; mismatch → `403`.

### 12.3. Streaming path — `POST /v1/chat`

```
1. Resolve user_id from JWT                                   (§12.1)
2. Create conversation + session_state if conversation_id is None; else ownership-check   (§12.2)
3. session_state = await get_session_state(user_id, conversation_id)
4. Consume pending_persona → persona_to_inject; write current_persona; clear pending      (§6.3)
5. Build graph_input: user_id, user_input, conversation_id, session_state, persona_to_inject
6. state = {}; state.update(await retrieve_memory_node({**graph_input, **state}))
             state.update(await assemble_prompt_node({**graph_input, **state}))
7. Stream LLMFactory.get_llm(streaming=True).astream(state["final_prompt"])
8. On stream completion: asyncio.create_task(background_tasks(...))                       (§12.4)
```

> **Step 6 — nodes return PARTIAL state updates and must be merged, not assigned.** `state = await retrieve_memory_node(state)` discards `user_input`, `session_state`, and `persona_to_inject`, and `assemble_prompt_node` then raises `KeyError`. Always merge.

The compiled `cliona_graph` is **not** invoked here (§4.4).

**SSE event format `[B8]`** — every event carries a `type` discriminator:

```
data: {"type": "conversation", "conversation_id": "<uuid>"}   # first event, only on creation
data: {"type": "token", "content": "Fuck"}
data: {"type": "token", "content": " her"}
data: {"type": "token", "content": ", bro."}
data: {"type": "end"}
data: {"type": "error", "message": "<safe message>"}          # terminal on failure
```

`media_type="text/event-stream"`.

### 12.4. Background task

Fire-and-forget via `asyncio.create_task`, started after streaming completes. Wrapped in try/except — a failure here must never surface to the user, but must be logged.

Performs exactly four things, in order:

1. **Persist messages `[A4]`.** Embed both the user message and the full assistant response with `get_embedding()` (384d), then insert **two rows** into `messages` — one `role='user'`, one `role='assistant'` — each carrying both `conversation_id` and `user_id`. Then set `conversations.updated_at = NOW()` and `conversations.last_message_at = NOW()`. **This is the only writer to `messages`. Without it the vector index stays empty and semantic recall silently returns nothing.**
2. **Classify** the user message → `Optional[str]` (§6.2).
3. **Evaluate the persona rule** → `pending_persona` (§6.3).
4. **Write `session_state`** — `turn_count + 1`, `pending_persona`, `last_3_messages[-6:]`, `updated_at` — in a single update (§7).

---

## 13. Decision Log

Resolved contradictions between the source docs. Settled. Do not reopen.

| ID | Decision |
| :--- | :--- |
| A1 | `messages` carries a denormalized `user_id`; vector search is user-scoped and cross-conversation. |
| A2 | Clerk `sub` → internal UUID via upsert on `users.clerk_id`. Clerk IDs never enter queries. |
| A3 | `DATABASE_URL` is its own env var (`postgresql+asyncpg://`). Never derived from `SUPABASE_URL`. |
| A4 | The background task embeds and inserts both messages. It is the sole writer to `messages`. |
| A5 | `/v1/chat` creates the conversation **and** its `session_state` row when `conversation_id` is null; the id is the first SSE event. |
| A6 | Clerk RS256 verified against JWKS, not `CLERK_SECRET_KEY`. |
| B1 | Classifier returns `None` below 0.3. Inject on `classified != current_persona` **or** `turn_count % 5 == 0`. `current_persona` written on consumption. **Turn 1 injects no persona.** No `casual` fallback. |
| B2 | `last_3_messages` holds 6 entries (3 turns), `[-6:]`. Column name unchanged. |
| B3 | 7-layer prompt. No `CONVERSATION_SUMMARY`. `conversations.summary` unused. |
| B4 | Janitor and Fact Extractor both out of scope; both depend on `user_facts` population that doesn't exist. |
| B5–B7 | 11-field `ClionaState`, 3-node graph. `generate_node` + `cliona_graph` retained as dead code, not deleted. |
| B8 | SSE events all carry `{"type": ...}`. |
| B9 | `/v1/chat` canonical. `conversations.py` added for the two GET routes; no `user_id` path param. |
| B10 | RLS off, `service_role` key, auth layer is the boundary. |
| B11 | `BACKEND.md` `Settings` canonical + `DATABASE_URL`. |
| B12 | React + `assistant-ui`. |
| B13 | One `session_state` row per conversation, keyed by `conversation_id`. |
| B14 | `db_models.py` and `session_manager.py` added to the tree. |
| B15 | Model slugs written as specified, flagged for verification before first deploy. |
| — | Retrieval returns plain dicts; consumers use key access (`fact["subject"]`). |
| — | Manual node invocation merges partial updates; never reassigns state. |
| — | Compiled graph is `cliona_graph`; FastAPI instance is `app`. |
| — | Absolute imports rooted at `app.`. |
| — | No role filter on semantic retrieval — both `user` and `assistant` messages are recallable. |
