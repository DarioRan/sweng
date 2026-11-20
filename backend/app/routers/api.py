"""The five §5.2 endpoints, plus GET /documents (US-28, an admin-dashboard addition).

/detect (app/vision/detector.py, T-201), /ask (app/rag/, ADR 0003 and 0004) and
/documents (app/corpus/indexer.py, reusing app/corpus/ingest.py, T-203b) are
implemented; /figures/{key} serves the figure or page image a citation names. figure
and transcribe return 501 with the contract they will honour: figure (T-207),
transcribe (T-403/T-406).
"""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from minio.error import S3Error
from PIL import UnidentifiedImageError
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.contracts import (
    AskRequest,
    AskResponse,
    BoundingBox,
    Detection,
    DetectResponse,
    DocumentUploadResponse,
    FigureKind,
    FigureResponse,
    ManualResponse,
    Provenance,
    TranscribeResponse,
)
from app.corpus.indexer import Indexer, get_indexer
from app.documents import DocumentStore
from app.rag.service import get_pipeline
from app.security import require_roles
from app.users import Role
from app.vision.detector import Detector, DetectorUnavailable

router = APIRouter(prefix="/api", tags=["contracts"])

REPAIR = [Depends(require_roles(Role.owner, Role.technician))]
CORPUS = [Depends(require_roles(Role.administrator))]

_NOT_IMPLEMENTED = HTTPException(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    detail="Contract fixed under T-202; behaviour arrives in a later sprint.",
)


MAX_PHOTO_BYTES = 10 * 1024 * 1024  # the client compresses to 2 MB (T-403); this is a guard
MAX_PDF_BYTES = 50 * 1024 * 1024


def get_detector(request: Request) -> Detector:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        detector = Detector(request.app.state.stores.settings.detector_weights)
        request.app.state.detector = detector
    return detector


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.documents


@router.post("/detect", response_model=DetectResponse, dependencies=REPAIR)
async def detect(
    image: Annotated[UploadFile, File()],
    job_id: Annotated[str, Form()],
    request: Request,
) -> DetectResponse:
    """The components in a photo, best first (T-201, Rule 2).

    Every candidate above a low floor is listed. `above_threshold` says whether the best one
    clears DETECTOR_CONFIDENCE_THRESHOLD: only then may the client name it or draw it.
    Below, the client shows the candidates with none selected, and search by name.
    """
    data = await image.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "photo over 10 MB")
    threshold = request.app.state.stores.settings.detector_confidence_threshold
    try:
        boxes, _, _ = await asyncio.to_thread(get_detector(request).detect, data)
    except DetectorUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err
    except UnidentifiedImageError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "not an image") from err
    detections = [
        Detection(
            label=b.label,
            box=BoundingBox(x=b.x, y=b.y, width=b.width, height=b.height),
            score=b.score,
        )
        for b in boxes
    ]
    return DetectResponse(
        detections=detections,
        above_threshold=bool(detections) and detections[0].score >= threshold,
    )


@router.post("/ask", response_model=AskResponse, dependencies=REPAIR)
async def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer from the manuals only, with citations, or abstain (Rules 1, 3, 4).

    An abstention is a normal 200 response with status 'abstained'. 503 means a part of
    the stack is not running, and says which.
    """
    settings = request.app.state.stores.settings
    try:
        pipeline = await get_pipeline(request.app)
        response, _ = await pipeline.ask(body.question, body.confirmed_component)
    except httpx.HTTPStatusError as err:  # Ollama answered, but not with an answer
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The language model refused the request ({err.response.status_code}). Is "
            f"{settings.llm_local_model} pulled? Run: docker compose exec ollama ollama pull "
            f"{settings.llm_local_model}",
        ) from err
    except httpx.HTTPError as err:  # Ollama is not reachable
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The language model at {settings.llm_local_url} does not answer "
            f"({type(err).__name__}). Start it with: docker compose --profile local up",
        ) from err
    except (ResponseHandlingException, UnexpectedResponse) as err:  # Qdrant
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The manual index is not available ({type(err).__name__}). Is the corpus indexed? "
            "Run: docker compose --profile ingest run --rm ingest",
        ) from err
    return response


@router.get("/figures/{key:path}")
async def figure_image(key: str, request: Request) -> Response:
    """The PNG a citation's `figure` names, or a page render (`pages/<manual>/p012.png`)."""
    stores = request.app.state.stores
    bucket = stores.settings.s3_bucket_figures
    try:
        obj = await asyncio.to_thread(stores.s3.get_object, bucket, key)
        data = obj.read()
    except S3Error as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no figure {key}") from err
    return Response(data, media_type="image/png")


@router.get("/figure", response_model=FigureResponse, dependencies=REPAIR)
async def figure(component: str, kind: FigureKind = FigureKind.exploded) -> FigureResponse:
    raise _NOT_IMPLEMENTED


@router.post("/transcribe", response_model=TranscribeResponse, dependencies=REPAIR)
async def transcribe(audio: Annotated[UploadFile, File()]) -> TranscribeResponse:
    raise _NOT_IMPLEMENTED


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=CORPUS,
)
async def upload_document(
    pdf: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    licence_basis: Annotated[str, Form()],
    retrieval_date: Annotated[str, Form()],
    indexer: Annotated[Indexer, Depends(get_indexer)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> DocumentUploadResponse:
    """Parse, chunk, embed and index the PDF (Rule 4, 5; app/corpus/ingest.py), and record
    its provenance. Indexing runs before this returns: an admin upload is rare and the
    manual must be searchable before the response says it is."""
    provenance = Provenance(
        source=source, licence_basis=licence_basis, retrieval_date=retrieval_date
    )
    data = await pdf.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "PDF over 50 MB")
    filename = pdf.filename or "manual.pdf"
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip() or filename
    document_id = f"{uuid.uuid4().hex[:8].upper()}-01"
    row = {
        "doc_code": document_id.rsplit("-", 1)[0],
        "revision": "01",
        "file_name": filename,
        "title": title,
        "components": "",  # not curated at upload time; retrieval scopes by component only
        "source_url": provenance.source,  # for manuals with no curated components
        "licence_basis": provenance.licence_basis,
        "retrieval_date": provenance.retrieval_date,
    }
    try:
        outcome = await indexer.index(row, data, filename)
    except Exception as err:  # noqa: BLE001 -- recorded as a failed upload, not a 500
        await store.create(
            document_id=document_id,
            title=title,
            source=provenance.source,
            licence_basis=provenance.licence_basis,
            retrieval_date=provenance.retrieval_date,
            pages=0,
            status="error",
            detail=f"{type(err).__name__}: {err}",
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Could not index the manual: {err}"
        ) from err
    doc_status = "indexed" if outcome.status == "ok" else "error"
    await store.create(
        document_id=document_id,
        title=title,
        source=provenance.source,
        licence_basis=provenance.licence_basis,
        retrieval_date=provenance.retrieval_date,
        pages=outcome.pages,
        status=doc_status,
        detail=None if doc_status == "indexed" else outcome.status,
    )
    return DocumentUploadResponse(document_id=document_id, indexing_job_id=str(uuid.uuid4()))


@router.get("/documents", response_model=list[ManualResponse], dependencies=CORPUS)
async def list_documents(
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> list[ManualResponse]:
    return [
        ManualResponse(
            document_id=d.document_id,
            title=d.title,
            source=d.source,
            licence_basis=d.licence_basis,
            retrieval_date=d.retrieval_date,
            pages=d.pages,
            status=d.status,
        )
        for d in await store.list_all()
    ]
