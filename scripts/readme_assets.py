"""Draw the README's hero (how a paper becomes an answer), light and dark, into docs/assets/.

One layout, two palettes, so the two versions cannot drift apart. Standard library only.

Flat boxes on an aligned grid, right-angled connectors, one accent color kept for the one thing
that matters (the corpus, and the paths into and out of it), labels in sentence case, a legend and
a note line. No shadows, no counts that would go stale.

Usage: uv run python scripts/readme_assets.py
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"
FONT = "ui-sans-serif, -apple-system, Segoe UI, Inter, Helvetica, Arial, sans-serif"


@dataclass(frozen=True)
class Palette:
    """The colors of one theme; light and dark share every other value."""

    paper: str
    surface: str
    ink: str
    grey: str
    hair: str
    rule: str  # connectors that are not the corpus path
    accent: str
    tint: str  # the corpus fill


LIGHT = Palette("#FDFDFB", "#FFFFFF", "#0E0E10", "#71716E", "#E4E3DE", "#A9A8A3", "#1F7A4D", "#EAF4EE")
DARK = Palette("#0E0E10", "#1C1C20", "#EDEDEA", "#A3A39D", "#2A2A2E", "#6F6F6B", "#5CC08A", "#12261B")


@dataclass(frozen=True)
class Box:
    """One step or tile: an eyebrow, a name and a one- or two-line description."""

    x: int
    y: int
    kind: str  # you | code | out | web
    eyebrow: str
    name: str
    what: str
    w: int = 230
    h: int = 100


# ---- the grid ----
W, H = 1600, 930
M = 56
SIDE_W, OUT_X = 260, 1214
COL = (380, 650, 920)  # the three center columns, 230 wide, 40 apart
SRC_Y, ROW1, CORPUS_Y, CORPUS_H, ROW3 = 290, 390, 540, 76, 660
PAD, CHAR_PX, MAX_LINES = 18, 7.4, 2

SOURCE = Box(COL[0], SRC_Y, "web", "LOOKED UP", "doi.org, Crossref", "", h=60)
INPUTS = [
    Box(M, ROW1, "you", "YOU", "Upload a paper", "geg-rag-upload; published versions only", SIDE_W),
    Box(M, ROW3, "you", "YOU", "Ask a question", "In the playground or just agent-query", SIDE_W),
]
INGEST = [
    Box(COL[0], ROW1, "code", "01  UPLOADER", "Name", "Finds the DOI, names the file, skips copies"),
    Box(COL[1], ROW1, "code", "02  BUCKET", "Store", "One PDF per DOI, citation in its metadata"),
    Box(COL[2], ROW1, "code", "03  CLOUD FUNCTION", "Import", "Into the corpus on every upload"),
]
ANSWER = [
    Box(COL[0], ROW3, "code", "04  AGENT", "Retrieve", "Searches the corpus, nothing else"),
    Box(COL[1], ROW3, "code", "05  CALLBACK", "Check", "Not backed by the chunks: abstain"),
    Box(COL[2], ROW3, "code", "06  RENDERING", "Cite", "Author, year, title, DOI, excerpts"),
]
OUTPUTS = [
    Box(OUT_X, ROW1, "out", "OUTPUT", "A shared library", "Flat, deduplicated, one name per DOI", 330),
    Box(
        OUT_X,
        ROW3 - 50,
        "out",
        "OUTPUT",
        "An answer with sources",
        "Cited, with the excerpts it rests on",
        330,
        84,
    ),
    Box(OUT_X, ROW3 + 66, "out", "OR", "A fixed sentence", "No paper on it, no answer", 330, 84),
]


def text(x: float, y: float, s: str, size: float, fill: str, weight: int = 400, spacing: float = 0) -> str:
    """One line of text, escaped."""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}"{ls}>'
        f"{escape(s)}</text>"
    )


def lines_of(b: Box) -> list[str]:
    """The description's lines, or an error naming the box: text never touches an edge."""
    chars = int((b.w - 2 * PAD) / CHAR_PX)
    lines = textwrap.wrap(b.what, chars) if b.what else []
    if len(lines) > MAX_LINES or len(b.name) * 10.5 > b.w - 2 * PAD:
        raise SystemExit(f"{b.name}: {b.what!r} does not fit in {b.w}px; shorten it")
    return lines


def box(b: Box, p: Palette) -> str:
    """A tile with a left bar in its kind's color; an outside source is dashed and has no bar."""
    bar = {"you": p.ink, "code": p.rule, "out": p.accent, "web": p.rule}[b.kind]
    dash = ' stroke-dasharray="5 4"' if b.kind == "web" else ""
    parts = [
        f'<rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" rx="8" fill="{p.surface}" '
        f'stroke="{p.hair if b.kind != "web" else p.rule}"{dash}/>',
    ]
    if b.kind != "web":
        parts.append(f'<rect x="{b.x}" y="{b.y}" width="4" height="{b.h}" fill="{bar}"/>')
    parts.append(text(b.x + PAD, b.y + 26, b.eyebrow, 11, p.grey, 600, 1.6))
    parts.append(text(b.x + PAD, b.y + 50, b.name, 19, p.ink, 700))
    for i, line in enumerate(lines_of(b)):
        parts.append(text(b.x + PAD, b.y + 74 + 19 * i, line, 14, p.grey))
    return "".join(parts)


def path(pts: list[tuple[float, float]], color: str, marker: str, width: float = 1.6) -> str:
    """A right-angled connector through ``pts``, with an arrowhead at the end."""
    d = " ".join(f"{'M' if i == 0 else 'L'} {x} {y}" for i, (x, y) in enumerate(pts))
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" marker-end="url(#{marker})"/>'


def marker(name: str, color: str) -> str:
    """An arrowhead in one color."""
    return (
        f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
    )


def connectors(p: Palette) -> str:
    """Every arrow; only the two that enter and leave the corpus carry the accent."""
    r1, r3 = ROW1 + 50, ROW3 + 50
    right = COL[2] + 230
    out = [
        path([(M + SIDE_W, r1), (COL[0] - 4, r1)], p.rule, "r"),
        path([(M + SIDE_W, r3), (COL[0] - 4, r3)], p.rule, "r"),
        path([(COL[0] + 115, SRC_Y + 60), (COL[0] + 115, ROW1 - 4)], p.rule, "r"),
        path([(COL[0] + 230, r1), (COL[1] - 4, r1)], p.rule, "r"),
        path([(COL[1] + 230, r1), (COL[2] - 4, r1)], p.rule, "r"),
        path([(right, r1), (OUT_X - 4, r1)], p.rule, "r"),
        # the corpus path: in from the import, out to the retrieval
        path([(COL[2] + 115, ROW1 + 100), (COL[2] + 115, CORPUS_Y - 4)], p.accent, "a", 2.2),
        path([(COL[0] + 115, CORPUS_Y + CORPUS_H), (COL[0] + 115, ROW3 - 4)], p.accent, "a", 2.2),
        path([(COL[0] + 230, r3), (COL[1] - 4, r3)], p.rule, "r"),
        path([(COL[1] + 230, r3), (COL[2] - 4, r3)], p.rule, "r"),
        path([(right, r3), (right + 32, r3), (right + 32, ROW3 - 8), (OUT_X - 4, ROW3 - 8)], p.rule, "r"),
        # an abstain leaves at the check and carries no citations
        path([(COL[1] + 115, ROW3 + 100), (COL[1] + 115, ROW3 + 130), (OUT_X - 4, ROW3 + 130)], p.rule, "r"),
    ]
    return "".join(out)


def corpus(p: Palette) -> str:
    """The corpus band between the two rows, the one accent-filled shape."""
    x, w = COL[0], COL[2] + 230 - COL[0]
    return (
        f'<rect x="{x}" y="{CORPUS_Y}" width="{w}" height="{CORPUS_H}" rx="8" fill="{p.tint}" '
        f'stroke="{p.accent}" stroke-width="1.6"/>'
        + text(x + 260, CORPUS_Y + 30, "VERTEX AI RAG CORPUS", 11, p.accent, 700, 1.6)
        + text(
            x + 260, CORPUS_Y + 55, "Every uploaded paper. The only thing the agent reads.", 17, p.ink, 700
        )
    )


def hero(p: Palette) -> str:
    """The whole hero in one palette."""
    title = "Every answer comes from a paper the group uploaded, or there is no answer"
    desc = (
        "On the left, what people do: upload a published paper with geg-rag-upload, and ask a question. "
        "Uploading: the uploader finds the DOI, confirmed at doi.org or Crossref, names the file by it and "
        "skips copies; the bucket stores one PDF per DOI with the citation in its metadata; a Cloud Function "
        "imports it into the Vertex AI RAG corpus. Asking: the agent searches only the corpus, a callback "
        "abstains when the answer is not backed by the retrieved chunks, and rendering adds author, year, "
        "title, DOI and the excerpts. On the right, what you get: a shared library, an answer with sources, "
        "or a fixed sentence when no paper covers the question."
    )
    heads = [
        (M, "WHAT PEOPLE DO", SIDE_W),
        (COL[0], "HOW A PAPER BECOMES AN ANSWER", 770),
        (OUT_X, "WHAT YOU GET", 330),
    ]
    head_svg = "".join(
        text(x, 250, s, 12, p.ink, 700, 2)
        + f'<rect x="{x}" y="262" width="{w}" height="1.5" fill="{p.ink}"/>'
        for x, s, w in heads
    )
    boxes = "".join(box(b, p) for b in [SOURCE, *INPUTS, *INGEST, *ANSWER, *OUTPUTS])
    ly = H - 70
    legend = (
        f'<rect x="{M}" y="{ly - 30}" width="{W - 2 * M}" height="1" fill="{p.hair}"/>'
        + f'<rect x="{M}" y="{ly - 13}" width="4" height="18" fill="{p.ink}"/>'
        + text(M + 14, ly, "You: the only manual steps", 14, p.grey)
        + f'<rect x="{M + 270}" y="{ly - 13}" width="4" height="18" fill="{p.rule}"/>'
        + text(M + 284, ly, "Code in this repository", 14, p.grey)
        + f'<rect x="{M + 560}" y="{ly - 13}" width="18" height="18" rx="3" fill="none" '
        f'stroke="{p.rule}" stroke-dasharray="4 3"/>'
        + text(M + 588, ly, "Outside: looked up, not stored", 14, p.grey)
        + text(
            M,
            ly + 32,
            "Note: the agent never falls back to general knowledge. No paper, no answer.",
            14,
            p.grey,
        )
    )
    sub1 = "Upload a published PDF once: it is named by its DOI and imported into the corpus."
    sub2 = "The agent answers only from that corpus and cites author, year, title and DOI."
    size = f'viewBox="0 0 {W} {H}" width="{W}" height="{H}"'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" {size} role="img" aria-labelledby="ht hd">
  <title id="ht">{escape(title)}</title>
  <desc id="hd">{escape(desc)}</desc>
  <defs>{marker("r", p.rule)}{marker("a", p.accent)}</defs>
  <rect width="{W}" height="{H}" fill="{p.paper}"/>
  <g font-family="{FONT}">
    {text(M, 70, "LITERATURE RAG  ·  GEG GROUP", 12, p.accent, 700, 1.6)}
    {text(M, 124, title + ".", 36, p.ink, 800, -0.8)}
    {text(M, 166, sub1, 18, p.grey)}
    {text(M, 192, sub2, 18, p.grey)}
    {head_svg}
    {connectors(p)}
    {corpus(p)}
    {boxes}
    {legend}
  </g>
</svg>
"""


def main() -> None:
    """Write hero-light.svg and hero-dark.svg."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, palette in (("light", LIGHT), ("dark", DARK)):
        (OUT / f"hero-{name}.svg").write_text(hero(palette), encoding="utf-8")


if __name__ == "__main__":
    main()
