"""The five interface contracts fixed in §5.2 (T-202).

These are the request and response shapes the four tracks build against.
Behaviour behind them arrives in later sprints; the shapes should not move
without an ADR.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


# ------------------------------------------------------------ POST /detect
class BoundingBox(BaseModel):
    """Pixel coordinates on the submitted image, origin top-left."""

    x: int
    y: int
    width: int
    height: int


class Detection(BaseModel):
    label: str
    box: BoundingBox
    score: float = Field(ge=0.0, le=1.0)


class DetectResponse(BaseModel):
    """Sorted by score, highest first. An empty list is a valid answer (Rule 2)."""

    detections: list[Detection]
    above_threshold: bool


# --------------------------------------------------------------- POST /ask
class AnswerStatus(StrEnum):
    answered = "answered"
    abstained = "abstained"  # Rule 1: below retrieval confidence, no model call
    truncated = "truncated"  # Rule 3: stopped at a professional-only step


class Citation(BaseModel):
    document_id: str
    document_title: str
    page: int
    figure: str | None = None
    chunk_id: str


class Source(BaseModel):
    """Rule 4: every passage is attributable, and non-manufacturer sources are declared."""

    document_id: str
    document_title: str
    is_manufacturer_manual: bool


class Hazard(BaseModel):
    """Rule 3: stated ahead of the step it concerns."""

    before_step: int
    text: str
    professional_only: bool = False


class Step(BaseModel):
    number: int
    text: str
    citation: Citation


class AskRequest(BaseModel):
    question: str
    job_id: str
    confirmed_component: str | None = None


class AskResponse(BaseModel):
    status: AnswerStatus
    steps: list[Step] = []
    citations: list[Citation] = []
    sources: list[Source] = []
    hazards: list[Hazard] = []
    confidence: float = Field(ge=0.0, le=1.0)
    stop_reason: str | None = None  # set when status is truncated


# --------------------------------------------------------------- GET /figure
class FigureKind(StrEnum):
    exploded = "exploded"
    assembly = "assembly"


class FigureResponse(BaseModel):
    """Rule 5: the manual's own figure, with its caption, document and page."""

    image_url: str
    caption: str
    document_id: str
    document_title: str
    page: int


# --------------------------------------------------------- POST /transcribe
class TranscribeResponse(BaseModel):
    """Always shown to the user for confirmation before it becomes a question (FR-07)."""

    transcript: str
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------- POST /documents
class Provenance(BaseModel):
    source: str
    licence_basis: str
    retrieval_date: str  # ISO-8601 date


class DocumentUploadResponse(BaseModel):
    document_id: str
    indexing_job_id: str
