from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import chat, conversations, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO (later phase): load static/prompts/prompts.json into
    #   app.graph.nodes.SYSTEM_PROMPT and app.graph.nodes.DYNAMIC_PROMPTS
    # TODO (later phase): load static/lore/cliona_lore.json into
    #   app.graph.nodes.LORE
    # TODO (later phase): validate DYNAMIC_PROMPTS contains exactly the 8
    #   persona keys from CLAUDE.md §6.1 and fail fast on mismatch (§11.3)
    yield


app = FastAPI(title="Cliona", lifespan=lifespan)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(conversations.router)
