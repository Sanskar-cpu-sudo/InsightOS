"""
config.py
---------
Single source of truth for all settings in InsightOS.

Why this file exists:
Instead of hardcoding things like database URLs or API keys inside
agents/routers (which makes them impossible to reconfigure later),
every setting is read once here from environment variables (.env file)
and imported wherever it's needed.

This is a very standard production pattern: "12-factor config".
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- App identity ---
    APP_NAME: str = "InsightOS"
    ENV: str = "development"  # development | production

    # --- PostgreSQL ---
    # Example: postgresql://insightos:insightos@localhost:5432/insightos
    DATABASE_URL: str = "postgresql://insightos:insightos@localhost:5432/insightos"

    # --- Qdrant (vector store for Knowledge Agent) ---
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "insightos_documents"

    # --- LLM Gateway (LiteLLM) ---
    # We keep provider + model separate from API keys so switching
    # providers later (GPT -> Groq -> Gemini) is a one-line change.
    LLM_PROVIDER: str = "groq"           # openai | groq | gemini
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # model name passed to litellm (Groq model)
    # If the primary model/call fails (timeout, rate limit, outage), we fall
    # back to this smaller/faster model on the SAME provider before giving up.
    # Kept same-provider for V1 so only one API key is required to work.
    LLM_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LOGFIRE_TOKEN: str = ""

    # --- Embeddings (Knowledge Agent) ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Decision Agent thresholds (used by guardrails.py later) ---
    MIN_CONFIDENCE_TO_SHOW: float = 0.55  # below this, we flag "low confidence"

    # --- Data Agent settings ---
    ANOMALY_LOOKBACK_DAYS: int = 30  # how many past days count as "normal" baseline

    # --- Knowledge Agent / Re-ranker settings (V2) ---
    # We fetch more candidates than we actually need, then re-rank them
    # using similarity + recency + reliability, and keep only the best few.
    RERANK_CANDIDATE_COUNT: int = 20  # how many candidates to fetch from Qdrant
    FINAL_EVIDENCE_COUNT: int = 5      # how many to keep after re-ranking
    RECENCY_HALF_LIFE_DAYS: float = 7.0  # recency score halves every N days of age

    # --- Re-ranker combination weights (Step 1.7) ---
    # final_score = SIMILARITY_WEIGHT * similarity
    #             + RECENCY_WEIGHT    * recency
    #             + RELIABILITY_WEIGHT * reliability
    # Kept here (not hardcoded in reranker.py) so the balance between
    # "how well it matches", "how new it is", and "how trustworthy the
    # source is" can be tuned per environment without touching code.
    # These three should add up to 1.0.
    SIMILARITY_WEIGHT: float = 0.60
    RECENCY_WEIGHT: float = 0.25
    RELIABILITY_WEIGHT: float = 0.15

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """
    Cached so we don't re-read environment variables on every import.
    Usage elsewhere: `from app.config import get_settings; settings = get_settings()`
    """
    return Settings()