from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # statement_cache_size=0: DATABASE_URL is Supabase's transaction-mode pgbouncer
    # pooler, which doesn't support server-side prepared statements across pooled
    # backend connections — asyncpg's default caching collides under connection churn.
    connect_args={"ssl": True, "statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()
