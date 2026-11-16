"""Builds the /ask pipeline from the settings, once, on the first question.

Loading the embedder takes seconds, and downloads it the first time,
so it waits for the first /ask instead of slowing every start (and every test).
"""

import asyncio

from fastapi import FastAPI, HTTPException, status
from minio import Minio
from minio.error import S3Error
from qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.corpus.ingest import page_key
from app.rag.generation import OllamaVisionModel
from app.rag.pipeline import AskPipeline
from app.rag.pipeline import Settings as PipelineSettings
from app.rag.retrieval import Retriever

_lock = asyncio.Lock()


class BucketImages:
    def __init__(self, s3: Minio, bucket: str) -> None:
        self.s3, self.bucket = s3, bucket

    def page(self, document_id: str, page: int) -> bytes | None:
        try:
            return self.s3.get_object(self.bucket, page_key(document_id, page)).read()
        except S3Error:
            return None


def build(settings: Settings, s3: Minio) -> AskPipeline:
    if settings.llm_backend != "local":
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_BACKEND=hosted, but there is no hosted model: the team uses local models "
            "only (ADR 0003). Set LLM_BACKEND=local.",
        )
    retriever = Retriever(
        QdrantClient(url=settings.qdrant_url),
        settings.qdrant_collection,
        settings.embedder_model,
        settings.retrieval_scorer,
        cache_dir=settings.model_cache_dir,
    )
    model = OllamaVisionModel(
        settings.llm_local_url, settings.llm_local_model, settings.llm_timeout_s
    )
    return AskPipeline(
        retriever,
        model,
        BucketImages(s3, settings.s3_bucket_figures),
        PipelineSettings(settings.retrieval_confidence_threshold, settings.ask_page_images),
    )


async def get_pipeline(app: FastAPI) -> AskPipeline:
    pipeline = getattr(app.state, "ask_pipeline", None)
    if pipeline is None:
        async with _lock:
            pipeline = getattr(app.state, "ask_pipeline", None)
            if pipeline is None:
                settings = get_settings()
                pipeline = await asyncio.to_thread(build, settings, app.state.stores.s3)
                app.state.ask_pipeline = pipeline
    return pipeline
