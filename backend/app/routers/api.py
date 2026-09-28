"""The five §5.2 endpoints, as typed stubs.

Each returns 501 with the contract it will honour, so the frontend and the
tests can be written against real shapes now and swapped for behaviour later:
detect (T-201/T-208), ask (T-205/T-501/T-502/T-503/T-505), figure (T-207),
transcribe (T-403/T-406), documents (T-203b).
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.contracts import (
    AskRequest,
    AskResponse,
    DetectResponse,
    DocumentUploadResponse,
    FigureKind,
    FigureResponse,
    Provenance,
    TranscribeResponse,
)

router = APIRouter(prefix="/api", tags=["contracts"])

_NOT_IMPLEMENTED = HTTPException(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    detail="Contract fixed under T-202; behaviour arrives in a later sprint.",
)


@router.post("/detect", response_model=DetectResponse)
async def detect(
    image: Annotated[UploadFile, File()],
    job_id: Annotated[str, Form()],
) -> DetectResponse:
    raise _NOT_IMPLEMENTED


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    raise _NOT_IMPLEMENTED


@router.get("/figure", response_model=FigureResponse)
async def figure(component: str, kind: FigureKind = FigureKind.exploded) -> FigureResponse:
    raise _NOT_IMPLEMENTED


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(audio: Annotated[UploadFile, File()]) -> TranscribeResponse:
    raise _NOT_IMPLEMENTED


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(
    pdf: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    licence_basis: Annotated[str, Form()],
    retrieval_date: Annotated[str, Form()],
) -> DocumentUploadResponse:
    Provenance(source=source, licence_basis=licence_basis, retrieval_date=retrieval_date)
    raise _NOT_IMPLEMENTED
