"""Split one manual page into chunks for the vector index.

A page is one chunk whenever it fits the embedder, so the steps on a page stay together
and every chunk cites exactly one page. A longer page is cut between steps.

Sizes are measured by a function the caller passes in: the embedder's own token count.
Characters are a poor guide, a contents page is close to one token per character.
No dependencies, so the tests need neither a PDF nor a store.
"""

import re
from collections.abc import Callable, Iterator

# A step starts with "1. " in the older manuals and is a bare "1" line in the newer ones.
_STEP = re.compile(r"\d{1,2}(\. |$)")
# Printed on every continuation page; it says nothing about the repair.
_FURNITURE = {"to be continued on next page"}
# Bookmarks Word made for itself: "O_24584", filed under a folder with a Japanese name.
_NOT_A_HEADING = re.compile(r"O_\d+|.*[\u3040-\u30ff\u4e00-\u9fff].*")


_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
# The last page of every manual ends with a line such as "(c) Apr. 2025 by SHIMANO INC."
_PRINTED = re.compile(r"([A-Za-z]{3})[a-z]*\.? ?(\d{4}) by shimano", re.IGNORECASE)


def published(last_page: str) -> str:
    """When the manual was printed, as 'YYYY-MM', read from its last page. '' if not found."""
    match = _PRINTED.search(" ".join(last_page.split()))
    if not match or match.group(1).lower() not in _MONTHS:
        return ""
    return f"{match.group(2)}-{_MONTHS.index(match.group(1).lower()) + 1:02d}"


def heading(title: str) -> str:
    """A bookmark title tidied into a section name, or '' if it is not a real heading."""
    title = re.sub(r"[\ue000-\uf8ff]", "", title)  # a bullet from a symbol font
    title = " ".join(title.split())
    return "" if _NOT_A_HEADING.fullmatch(title) else title


def page_sections(bookmarks: list[tuple[int, str]], pages: int) -> list[str]:
    """For each page, the section it falls under.

    `bookmarks` are (page index, 'INSTALLATION > Brake hose') in document order. A page
    where several sections start names them all; a page before the first one gives ''.
    """
    starts: dict[int, list[str]] = {}
    for page, title in bookmarks:
        here = starts.setdefault(page, [])
        # "INSTALLATION" is dropped once "INSTALLATION > Brake hose" starts on the same page.
        here[:] = [t for t in here if not title.startswith(t + " > ")] + [title]
    labels, current = [], ""
    for page in range(pages):
        if page in starts:
            current = starts[page][-1]
            labels.append(" | ".join(starts[page]))
        else:
            labels.append(current)
    return labels


def clean(text: str) -> str:
    """Tidy extracted page text: no runs of spaces, dots or blank lines, no trailing spaces."""
    text = re.sub(r"\.{4,}", " ... ", text)  # leader dots on a contents page
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def body(text: str, page_number: int) -> str:
    """The page without what the layout repeats on every page: its number, 'to be continued'."""
    lines = [line for line in clean(text).split("\n") if line.lower() not in _FURNITURE]
    # The number is the first line in some manuals and the last in others. Take one only.
    for edge in (-1, 0):
        if lines and lines[edge] == str(page_number):
            del lines[edge]
            break
    return "\n".join(lines).strip()


def _steps(text: str) -> list[str]:
    """The page as units that should not be cut: each step with the lines that follow it."""
    units: list[list[str]] = [[]]
    for line in text.split("\n"):
        if _STEP.match(line) and units[-1]:
            units.append([])
        units[-1].append(line)
    return ["\n".join(unit) for unit in units]


def _fitting(text: str, limit: int, size: Callable[[str], int]) -> Iterator[str]:
    """Pieces of `text` that each fit `limit`: whole steps, else lines, else words."""
    for step in _steps(text):
        if size(step) <= limit:
            yield step
            continue
        for line in step.split("\n"):
            if size(line) <= limit:
                yield line
                continue
            piece = ""
            for word in line.split(" "):
                while size(word) > limit:  # one unbroken run longer than a whole chunk
                    if piece:
                        yield piece
                        piece = ""
                    yield word[: limit // 2]
                    word = word[limit // 2 :]
                if piece and size(f"{piece} {word}") > limit:
                    yield piece
                    piece = word
                else:
                    piece = f"{piece} {word}" if piece else word
            if piece:
                yield piece


def chunk_page(text: str, limit: int, size: Callable[[str], int] = len) -> list[str]:
    """The chunks of one page, in reading order. Every character of the page is in exactly one.

    Pieces are packed into a chunk until the next one would pass `limit`. `size` must not
    report more than one unit per character plus a small constant, which holds for
    characters and for tokens (a tokenizer adds two markers to whatever it counts).
    """
    chunks: list[str] = []
    current = ""
    for piece in _fitting(text, limit, size):
        joined = f"{current}\n{piece}" if current else piece
        if current and size(joined) > limit:
            chunks.append(current)
            current = piece
        else:
            current = joined
    if current.strip():
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]
