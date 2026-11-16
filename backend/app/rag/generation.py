"""The vision-language model: it reads the passages and their pages, and writes the answer.

The model gets only what the gates let through (gate.py, hazards.py): the passages of one
manual as text, and the rendered pages they come from as images, so a table or a figure
can be read as printed rather than as flattened text. It answers in a JSON shape enforced
by Ollama, and every step must name the passages it was taken from. grounding.py then
checks it.

The model is not fine-tuned and is not asked for warnings. What keeps it to the manuals
is that it sees nothing else, the prompt, the enforced shape, and the check after it.
Hazards come from the hazard list, never from the model (hazards.py).
"""

import base64
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.rag.retrieval import Passage
from app.rag.text import part_codes

SYSTEM_PROMPT = """\
You are a bicycle repair assistant. You answer from the manual passages and the manual \
pages you are given, and from nothing else.

Rules:
1. Use only the passages and pages. Never use what you remember about bicycle parts.
2. Check the part code in the question. A passage about another part, or about another \
bolt, does not answer it. A passage whose manual covers the part applies to it, unless \
the passage names other models for that value.
3. If they do not contain the answer, set "status" to "abstained" and give no steps.
4. Otherwise set "status" to "answered". For a value (torque, size, tool), give one step \
that states it exactly as printed. For a procedure, give the steps in order, one action \
each. Never round or convert a value.
5. If the passages say the job must be left to a dealer or a professional, set "status" \
to "professional_only", give the steps up to that point only, and put the manual's words \
in "stop_reason".
6. Every step lists in "passages" the ids of the passages it was taken from, for example \
["P2"]. A page image shows the page of the passages named under it; cite the passage.

Reply with one JSON object and nothing else."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "abstained", "professional_only"]},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "passages": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "passages"],
            },
        },
        "stop_reason": {"type": "string"},
    },
    "required": ["status", "steps"],
}

# Temperature 0 and a fixed seed: the same question and passages give the same answer.
# The context holds five passages and two page images (about 1,300 tokens each).
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 8192, "num_predict": 1024}


@dataclass
class PageImage:
    document_id: str
    page: int
    png: bytes
    passage_ids: list[str]  # the passages printed on this page


class VisionModel(Protocol):
    async def generate(self, system: str, user: str, images: list[bytes]) -> dict: ...


def passage_ids(passages: list[Passage]) -> dict[str, Passage]:
    return {f"P{n}": p for n, p in enumerate(passages, start=1)}


def build_prompt(question: str, passages: dict[str, Passage], images: list[PageImage]) -> str:
    codes = part_codes(question)
    blocks = []
    for pid, p in passages.items():
        head = (
            f"[{pid}] {p.document_title} ({p.document_id}), printed {p.published or 'unknown'}, "
            f"page {p.page}, {p.section or 'no section'}"
        )
        covered = sorted(codes & set(p.parts))
        if covered:  # a page often gives a value without repeating the models it applies to
            head += f"\nThis manual covers {', '.join(covered)}."
        blocks.append(f"{head}\n{p.text}")
    lines = ["Passages:", "", "\n\n".join(blocks), ""]
    if images:
        lines.append("Page images, in the order attached:")
        for n, image in enumerate(images, start=1):
            lines.append(
                f"Image {n}: {image.document_id} page {image.page}, "
                f"the page of {', '.join(image.passage_ids)}"
            )
        lines.append("")
    lines.append(f"Question: {question}")
    return "\n".join(lines)


class OllamaVisionModel:
    """Ollama's chat API. Thinking is off: with it on, qwen3.5:4b spent its whole output
    budget thinking and returned an empty answer (ADR 0003)."""

    def __init__(self, url: str, model: str, timeout: float = 120.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate(self, system: str, user: str, images: list[bytes]) -> dict:
        message: dict = {"role": "user", "content": user}
        if images:
            message["images"] = [base64.b64encode(png).decode() for png in images]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            reply = await client.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system}, message],
                    "format": ANSWER_SCHEMA,
                    "options": OPTIONS,
                    "think": False,
                    "stream": False,
                },
            )
        reply.raise_for_status()
        content = reply.json()["message"]["content"]
        try:
            return json.loads(content)
        except ValueError:
            return {"status": "invalid", "raw": content}
