import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "LedgerLens"
    ENV: str = "development"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./ledgerlens.db"
    )

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Elasticsearch
    ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
    ES_INDEX: str = os.getenv("ES_INDEX", "ledgerlens_chunks")
    ES_USERNAME: str = os.getenv("ES_USERNAME", "")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "")
    EMBEDDING_DIMS: int = 768

    # Auth & JWT
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET", "ledgerlens-super-secret-key-change-in-production-2026"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )

    # AI / LLM
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Microservices URLs
    IDENTITY_SERVICE_URL: str = os.getenv(
        "IDENTITY_SERVICE_URL", "http://localhost:8001"
    )
    INGESTION_SERVICE_URL: str = os.getenv(
        "INGESTION_SERVICE_URL", "http://localhost:8002"
    )
    RAG_SERVICE_URL: str = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
