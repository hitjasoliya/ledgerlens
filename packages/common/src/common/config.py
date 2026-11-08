from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    APP_NAME: str = "LedgerLens"
    ENV: Literal["development", "test", "production"] = "development"
    DATABASE_URL: str = "sqlite:///./ledgerlens.db"
    UPLOAD_DIR: Path = Path(__file__).resolve().parents[4] / "data" / "uploads"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)
    ES_HOST: str = "http://localhost:9200"
    ES_INDEX: str = "ledgerlens_chunks_v2"
    ES_USERNAME: str = ""
    ES_PASSWORD: str = ""
    EMBEDDING_DIMS: int = Field(default=768, gt=0)
    EMBEDDING_MODEL: str = "embeddinggemma"
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=256)
    OLLAMA_HOST: str = "http://localhost:11434"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    RAG_GENERATOR_ADAPTER: Literal["gemini", "deterministic"] = "gemini"
    AI_TIMEOUT_SECONDS: float = Field(default=120, gt=0)
    READINESS_TIMEOUT_SECONDS: float = Field(default=2, gt=0)
    JWT_SECRET: str = ""
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, gt=0)
    ADMIN_INITIAL_PASSWORD: str = ""
    IDENTITY_SERVICE_URL: str = "http://localhost:8001"
    INGESTION_SERVICE_URL: str = "http://localhost:8002"
    RAG_SERVICE_URL: str = "http://localhost:8003"
    CORS_ORIGINS: list[str] = Field(default_factory=list)
    REQUEST_TIMEOUT_SECONDS: float = Field(default=300, gt=0)
    # Parsing cost grows with pages; these keep one upload from monopolizing the host.
    UPLOAD_MAX_BYTES: int = Field(default=20 * 1024 * 1024, gt=0)
    UPLOAD_MAX_PAGES: int = Field(default=40, ge=1)
    UPLOAD_READ_BYTES: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    INGESTION_WORKERS: int = Field(default=1, ge=1, le=16)
    JOB_LEASE_SECONDS: int = Field(default=300, ge=10)
    PARSER_TIMEOUT_SECONDS: float = Field(default=180, gt=0)
    DOCLING_DEVICE: Literal["cpu", "cuda", "mps", "auto"] = "cpu"
    WORKER_POLL_SECONDS: float = Field(default=1, gt=0)
    CONVERSATION_LEASE_SECONDS: int = Field(default=300, ge=10)
    CHUNK_TOKENS: int = Field(default=512, ge=64)
    CHUNK_OVERLAP: int = Field(default=50, ge=0)
    GENERATION_CONTEXT_TOKENS: int = Field(default=12000, ge=512)

    @model_validator(mode="after")
    def validate_security_and_limits(self):
        insecure = {
            "ledgerlens-super-secret-key-change-in-production-2026",
            "changeme", "change-me", "secret", "admin123", "password", "postgrespassword", "postgres",
        }
        if self.RAG_GENERATOR_ADAPTER == "deterministic" and self.ENV != "test":
            raise ValueError("Deterministic generation is allowed only in an isolated test environment")
        if self.ENV != "test":
            if len(self.JWT_SECRET.encode()) < 32 or self.JWT_SECRET.lower() in insecure:
                raise ValueError("Supply a private JWT_SECRET of at least 32 bytes")
            if self.ADMIN_INITIAL_PASSWORD and (
                len(self.ADMIN_INITIAL_PASSWORD) < 12
                or self.ADMIN_INITIAL_PASSWORD.lower() in insecure
            ):
                raise ValueError("Supply a private initial administrator password of at least 12 characters")
            try:
                database = make_url(self.DATABASE_URL)
            except Exception:
                raise ValueError("Supply a valid DATABASE_URL") from None
            if database.get_backend_name() == "postgresql" and (database.password or "").lower() in insecure:
                raise ValueError("Replace the published PostgreSQL password before deployment")
        if len(self.ADMIN_INITIAL_PASSWORD.encode()) > 72:
            raise ValueError("Initial administrator password exceeds bcrypt's 72-byte limit")
        if self.CHUNK_OVERLAP >= self.CHUNK_TOKENS:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_TOKENS")
        if self.CONVERSATION_LEASE_SECONDS <= self.AI_TIMEOUT_SECONDS:
            raise ValueError("Conversation lease must outlive an AI request timeout")
        return self


settings = Settings()
