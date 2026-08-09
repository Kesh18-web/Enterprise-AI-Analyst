from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application Settings with environment variable overrides and validation."""

    # General Environment
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Firebase / Firestore
    FIREBASE_CREDENTIALS_PATH: str = "./firebase_credentials.json"
    # Firebase project ID — used for token verification without full service account
    FIREBASE_PROJECT_ID: str = "project-edadbb90-c880-4851-84d"
    # Full service account JSON string (set in Railway env vars for production)
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # Qdrant Vector Store
    QDRANT_MODE: str = "memory"  # Options: 'memory', 'cloud', 'local_host'
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None

    # LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    # LangSmith Observability
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "enterprise-ai-analyst"

    # Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
