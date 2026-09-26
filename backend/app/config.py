"""Runtime configuration, read from the environment (set by docker-compose.yml)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173"

    # Storage (§5)
    database_url: str = "postgresql+asyncpg://repair:repair@localhost:5432/repair"
    qdrant_url: str = "http://localhost:6333"
    s3_endpoint: str = "localhost:8333"
    s3_access_key: str = "repair"
    s3_secret_key: str = "repair-secret"
    s3_secure: bool = False
    s3_bucket_manuals: str = "manuals"
    s3_bucket_figures: str = "figures"
    s3_bucket_captures: str = "captures"

    # Model layer (NFR-05): every backend is replaceable without touching call sites.
    llm_backend: Literal["hosted", "local"] = "hosted"
    llm_hosted_api_key: str = ""
    llm_local_url: str = "http://localhost:11434"
    llm_local_model: str = "llama3.2:3b"
    embedder_model: str = "BAAI/bge-small-en-v1.5"
    detector_weights: str = "/models/detector.pt"

    # Thresholds behind Rules 1 and 2 (§1.3). Calibrated under T-502; placeholders until then.
    detector_confidence_threshold: float = 0.6
    retrieval_confidence_threshold: float = 0.5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
