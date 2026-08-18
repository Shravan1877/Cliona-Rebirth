import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import chat, conversations, health
from app.graph import nodes

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Exact 8 keys from CLAUDE.md §6.1. No aliases, no display names.
EXPECTED_PERSONA_KEYS = {
    "casual",
    "studying",
    "venting",
    "relationship_negative",
    "relationship_positive",
    "hype_bro",
    "deep_emotional",
    "working",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # §11.3 — static prompt assets, loaded once and held in RAM. No prompt
    # text is ever hardcoded in Python.
    with open(STATIC_DIR / "prompts" / "prompts.json", encoding="utf-8") as f:
        prompts = json.load(f)

    nodes.SYSTEM_PROMPT = prompts["system_prompt"]
    nodes.DYNAMIC_PROMPTS = prompts["dynamic_prompts"]

    actual_keys = set(nodes.DYNAMIC_PROMPTS.keys())
    if actual_keys != EXPECTED_PERSONA_KEYS:
        missing = EXPECTED_PERSONA_KEYS - actual_keys
        unexpected = actual_keys - EXPECTED_PERSONA_KEYS
        raise RuntimeError(
            "dynamic_prompts in prompts.json does not match the 8 persona keys in "
            f"CLAUDE.md §6.1. missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )

    with open(STATIC_DIR / "lore" / "cliona_lore.json", encoding="utf-8") as f:
        nodes.LORE = json.load(f)

    yield


app = FastAPI(title="Cliona", lifespan=lifespan)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(conversations.router)
