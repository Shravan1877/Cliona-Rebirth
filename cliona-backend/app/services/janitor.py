"""STUB ONLY — out of scope for v1 (CLAUDE.md §9, [B4]).

Depends on user_facts being populated, which it isn't. No nightly cron, no
dedupe, no contradiction resolution, no pruning, no semantic compression.
This file is a permanent stub for the lifetime of v1, not a Phase 1
placeholder to be filled in during a later phase. It must never be called
from any live path.
"""


def run_janitor(*args, **kwargs):
    raise NotImplementedError("Janitor is out of scope for v1 — CLAUDE.md §9")
