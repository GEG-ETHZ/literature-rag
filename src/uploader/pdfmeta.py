"""Read metadata, leading text and the visually largest line from a PDF."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

PAGES_TO_SCAN = 2
JUNK_TITLE_PREFIXES = ("microsoft word", "untitled", "coversheet", "doi:", "pii:")
JUNK_TITLE_SUFFIXES = (".doc", ".docx", ".tex", ".pdf", ".dvi", ".indd")
MIN_TITLE_LENGTH = 8


@dataclass(frozen=True)
class PdfInfo:
    """Everything the naming logic needs from a PDF."""

    metadata: dict[str, str]
    text: str
    largest_font_line: str | None


TITLE_REGION_OF_PAGE = 0.4
FONT_SIZE_TOLERANCE = 0.5


def line_style(line: dict[str, Any]) -> tuple[float, bool, str] | None:
    """Return (font size, bold, text) of a horizontal text line, or ``None`` for empty or rotated lines."""
    spans = line.get("spans", [])
    text = " ".join(span["text"].strip() for span in spans if span["text"].strip())
    horizontal = tuple(line.get("dir", (1, 0))) == (1, 0)
    if not spans or not horizontal or not text:
        return None
    return max(span["size"] for span in spans), any("bold" in span["font"].lower() for span in spans), text


def same_style(a: tuple[float, bool, str], b: tuple[float, bool, str]) -> bool:
    """Whether two lines share font size (within tolerance) and boldness, i.e. belong to the same heading."""
    return abs(a[0] - b[0]) <= FONT_SIZE_TOLERANCE and a[1] == b[1]


def largest_font_line(page: pymupdf.Page) -> str | None:
    """Return the most title-like heading on ``page``, joined over its lines.

    Only horizontal lines in the top ``TITLE_REGION_OF_PAGE`` of the page count, so captions, footers and
    the rotated arXiv stamp never win. Among lines in the largest font (within ``FONT_SIZE_TOLERANCE``),
    bold beats regular and longer beats shorter, which separates a title from a running header. Adjacent
    lines of the same style within the block are joined, because titles usually wrap.
    """
    limit = page.rect.height * TITLE_REGION_OF_PAGE
    blocks: list[list[tuple[float, bool, str]]] = []
    for block in page.get_text("dict")["blocks"]:
        styled = [line_style(ln) for ln in block.get("lines", []) if ln["bbox"][1] <= limit]
        blocks.append([st for st in styled if st is not None])
    candidates = [
        (b, i)
        for b, lines in enumerate(blocks)
        for i, st in enumerate(lines)
        if len(st[2]) >= MIN_TITLE_LENGTH
    ]
    if not candidates:
        return None
    largest = max(blocks[b][i][0] for b, i in candidates)
    top = [(b, i) for b, i in candidates if blocks[b][i][0] >= largest - FONT_SIZE_TOLERANCE]
    b, i = max(top, key=lambda bi: (blocks[bi[0]][bi[1]][1], len(blocks[bi[0]][bi[1]][2])))
    return join_heading(blocks[b], i)


def join_heading(lines: list[tuple[float, bool, str]], index: int) -> str:
    """Extend line ``index`` backwards and forwards over neighbours of the same style and join the texts."""
    first = index
    while first > 0 and same_style(lines[first - 1], lines[index]):
        first -= 1
    last = index
    while last + 1 < len(lines) and same_style(lines[last + 1], lines[index]):
        last += 1
    return " ".join(ln[2] for ln in lines[first : last + 1])


def read_pdf(path: Path, pages: int = PAGES_TO_SCAN) -> PdfInfo:
    """Open ``path`` and extract metadata, the first ``pages`` pages of text and the largest-font line."""
    with pymupdf.open(path) as doc:
        metadata = {k: v for k, v in (doc.metadata or {}).items() if isinstance(v, str) and v}
        first_pages = [doc[i] for i in range(min(pages, doc.page_count))]
        text = "\n".join(page.get_text() for page in first_pages)
        heading = largest_font_line(first_pages[0]) if first_pages else None
    return PdfInfo(metadata=metadata, text=text, largest_font_line=heading)


def is_junk_title(title: str) -> bool:
    """Return whether ``title`` is a file name or placeholder rather than a paper title."""
    lowered = title.strip().lower()
    return (
        len(lowered) < MIN_TITLE_LENGTH
        or lowered.startswith(JUNK_TITLE_PREFIXES)
        or lowered.endswith(JUNK_TITLE_SUFFIXES)
    )


def title_from(info: PdfInfo) -> str | None:
    """Return the best title guess: clean metadata title first, else the largest-font line."""
    metadata_title = info.metadata.get("title", "")
    if metadata_title and not is_junk_title(metadata_title):
        return metadata_title.strip()
    return info.largest_font_line
