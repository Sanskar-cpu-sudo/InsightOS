from pydantic_settings import BaseSettings
from functools import lru_cache
# BaseSettings is a Pydantic class that automatically loads configuration values.

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
    LLM_MODEL: str = "llama-3.3-70b-versatile"  
    LLM_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # --- Embeddings (Knowledge Agent) ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Decision Agent thresholds (used by guardrails.py later) ---
    MIN_CONFIDENCE_TO_SHOW: float = 0.55  # below this, we flag "low confidence"

    # --- Data Agent settings ---
    ANOMALY_LOOKBACK_DAYS: int = 30  # how many past days count as "normal" baseline

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