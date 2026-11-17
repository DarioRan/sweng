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
    qdrant_collection: str = "manual_chunks"
    s3_endpoint: str = "localhost:8333"
    s3_access_key: str = "repair"
    s3_secret_key: str = "repair-secret"
    s3_secure: bool = False
    s3_bucket_manuals: str = "manuals"
    s3_bucket_figures: str = "figures"
    s3_bucket_captures: str = "captures"

    # Model layer (NFR-05): every backend is replaceable without touching call sites.
    # Local only (ADR 0003): there is no hosted model. 'hosted' is kept for NFR-05's switch.
    llm_backend: Literal["hosted", "local"] = "local"
    llm_hosted_api_key: str = ""
    llm_local_url: str = "http://localhost:11434"
    llm_local_model: str = "qwen3.5:4b"  # ADR 0003
    llm_timeout_s: float = 120.0
    embedder_model: str = "BAAI/bge-small-en-v1.5"
    # What scores a retrieved passage against the question; the gate reads the score.
    # 'dense' is the embedder's own similarity. Any other value names a cross-encoder.
    retrieval_scorer: str = "dense"  # ADR 0004
    model_cache_dir: str | None = None  # fastembed's cache; FASTEMBED_CACHE_PATH also works
    ask_page_images: int = 2  # page renders sent to the model with the passages
    detector_weights: str = "/models/detector.pt"

    # Thresholds behind Rules 1 and 2 (§1.3).
    detector_confidence_threshold: float = 0.6  # placeholder until T-502
    # The score below which /ask abstains without calling the model. Calibrated by
    # `python -m app.rag.calibrate` (ADR 0004); rerun it when the embedder, the scorer or
    # the corpus changes.
    retrieval_confidence_threshold: float = 0.75

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
