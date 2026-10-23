"""Render a grounded answer together with the retrieved source excerpts.

These helpers run inside the deployed agent (via ``after_model_callback``), so
the excerpts become part of the agent's own response text. That way every
consumer sees them — the CLI (``scripts/query_agent.py``) *and* the Vertex AI
Agent Engine Playground UI, which only ever shows the agent's final message.

Kept deliberately free of ``google.adk`` imports so the rendering logic is
unit-testable on its own.

Output format is controlled at deploy time:
* ``AGENT_STRUCTURED_OUTPUT=0`` (default) -> plain text answer + a
  ``Source excerpts:`` section.
* ``AGENT_STRUCTURED_OUTPUT=1`` -> a JSON envelope ``{answer, citations[]}``.

Per-excerpt length is capped by ``AGENT_EXCERPT_MAX_CHARS`` (default 600; set
to 0 to disable truncation).
"""

import json
import os
import re
from typing import Any

_DEFAULT_EXCERPT_MAX_CHARS = 600

# Marker used to separate the model's answer from the appended excerpts. The CLI
# relies on this to recover the clean answer when building structured output.
EXCERPTS_HEADER = "Source excerpts:"

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def cited_indices(answer: str) -> set[int]:
    """1-based chunk indices the answer actually cites via ``[n]`` markers."""
    return {int(m) for m in _CITATION_PATTERN.findall(answer)}


def excerpt_max_chars() -> int:
    """Per-excerpt character cap from ``AGENT_EXCERPT_MAX_CHARS`` (0 = no cap)."""
    raw = os.environ.get("AGENT_EXCERPT_MAX_CHARS", str(_DEFAULT_EXCERPT_MAX_CHARS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_EXCERPT_MAX_CHARS
    return max(value, 0)


def structured_output_enabled() -> bool:
    """Whether the agent should emit a JSON envelope instead of plain text."""
    return os.environ.get("AGENT_STRUCTURED_OUTPUT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def citation_label(chunk: dict[str, Any]) -> str:
    """Human-readable source label for a chunk.

    Uses the paper metadata when present, as ``Author (Year). Title. https://doi.org/...``
    with missing parts left out, and falls back to the display name or URI. The
    metadata comes from the object's custom metadata (see ``src/agent/tools.py``);
    when absent this degrades gracefully to the filename.
    """
    title = chunk.get("title")
    if not title:
        return chunk.get("source_display_name") or chunk.get("source_uri") or "(unknown)"
    head = ", ".join(chunk.get("authors") or [])
    year = chunk.get("year")
    if year:
        head = f"{head} ({year})" if head else f"({year})"
    label = f"{head}. {title}" if head else str(title)
    journal = chunk.get("journal")
    if journal:
        label += f" ({journal})"
    doi = chunk.get("doi")
    if doi:
        label += f". https://doi.org/{doi}"
    return label


def render_plain(answer: str, chunks: list[dict[str, Any]]) -> str:
    """Append a ``Source excerpts:`` section to ``answer`` for the given chunks.

    Only the chunks the answer actually cites (via ``[n]``) are shown, so the
    excerpts match the citations rather than dumping every retrieved chunk. If
    the answer has no ``[n]`` citations, all chunks are shown as a fallback.
    """
    if not chunks:
        return answer

    cited = cited_indices(answer)
    shown = [c for c in chunks if c.get("index") in cited] if cited else chunks
    if not shown:
        shown = chunks

    max_chars = excerpt_max_chars()
    lines = [answer, "", EXCERPTS_HEADER]
    for c in shown:
        idx = c.get("index")
        label = citation_label(c)
        uri = c.get("source_uri") or ""
        score = c.get("score")
        score_str = f" vector_distance={score:.3f}" if isinstance(score, (int, float)) else ""
        text = (c.get("text") or "").strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        lines.append("")
        lines.append(f"[{idx}] {label}{score_str}")
        if uri and uri != label:
            lines.append(f"    {uri}")
        if text:
            quoted = "\n".join(f"    > {ln}" for ln in text.split("\n") if ln)
            lines.append(quoted)
    return "\n".join(lines)


def render_structured(answer: str, chunks: list[dict[str, Any]]) -> str:
    """JSON envelope with the answer and full (untruncated) citation chunks."""
    return json.dumps(
        {
            "answer": answer,
            "citations": [
                {
                    "index": c.get("index"),
                    "source_uri": c.get("source_uri"),
                    "source_display_name": c.get("source_display_name"),
                    "title": c.get("title"),
                    "authors": c.get("authors") or [],
                    "year": c.get("year"),
                    "doi": c.get("doi"),
                    "journal": c.get("journal"),
                    "score": c.get("score"),
                    "text": c.get("text"),
                }
                for c in chunks
            ],
        },
        indent=2,
    )


def render_answer(answer: str, chunks: list[dict[str, Any]]) -> str:
    """Render ``answer`` + ``chunks`` per the deploy-time output format."""
    if structured_output_enabled():
        return render_structured(answer, chunks)
    return render_plain(answer, chunks)
