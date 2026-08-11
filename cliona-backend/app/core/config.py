from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database — [A3] a real Postgres DSN, NOT derived from SUPABASE_URL
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host:5432/postgres

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # OpenRouter
    OPENROUTER_API_KEY: str
    LLM_MODEL_ID: str = "nvidia/nemotron-3-ultra-550b-a55b:free"

    # Clerk
    CLERK_SECRET_KEY: str
    CLERK_JWT_ISSUER: str = "https://clerk.your-domain.com"
    CLERK_JWKS_URL: str  # [A6] RS256 verification key source

    # Server
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
