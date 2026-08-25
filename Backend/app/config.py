"""
config.py
---------
Single source of truth for all settings in InsightOS.

All configuration is loaded from environment variables / .env.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- App identity ---
    APP_NAME: str = "InsightOS"
    ENV: str = "development"
    # --- PostgreSQL ---
    DATABASE_URL: str = (
        "postgresql://insightos:insightos@localhost:5432/insightos"
    )

    # --- Qdrant ---
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "insightos_documents"

    # --- LLM Gateway ---
    LLM_PROVIDER: str = "groq"

    # Groq model IDs
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_FALLBACK_MODEL: str = "openai/gpt-oss-20b"

    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # --- Monitoring ---
    LOGFIRE_TOKEN: str = ""

    # --- Embeddings ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Decision Agent ---
    MIN_CONFIDENCE_TO_SHOW: float = 0.55

    # --- Data Agent ---
    ANOMALY_LOOKBACK_DAYS: int = 30

    # --- Knowledge Agent / Re-ranker ---
    RERANK_CANDIDATE_COUNT: int = 20
    FINAL_EVIDENCE_COUNT: int = 5
    RECENCY_HALF_LIFE_DAYS: float = 7.0

    # --- Re-ranker weights ---
    SIMILARITY_WEIGHT: float = 0.60
    RECENCY_WEIGHT: float = 0.25
    RELIABILITY_WEIGHT: float = 0.15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached so configuration is loaded once.
    """
    return Settings()