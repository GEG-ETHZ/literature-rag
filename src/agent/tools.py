"""Function tool that queries the configured Vertex AI RAG corpus."""

import logging
import os
from functools import lru_cache
from typing import Any

import google.cloud.storage as storage
from vertexai.preview import rag

logger = logging.getLogger(__name__)

# Custom metadata that geg-rag-upload writes on every object (see src/uploader/cli.py).
# Read at query time to turn a file name into a readable citation.
METADATA_KEYS = ("doi", "title", "year", "first_author")


@lru_cache(maxsize=1)
def storage_client() -> storage.Client:
    """Cloud Storage client, built once per process.

    Constructing a client re-runs credential discovery, so building one per
    lookup would add that cost to every retrieval on the query hot path.
    """
    return storage.Client()


def split_gcs_uri(gcs_uri: str) -> tuple[str, str] | None:
    """Return ``(bucket, object name)`` for a ``gs://bucket/name`` URI, else ``None``."""
    if not gcs_uri.startswith("gs://"):
        return None
    bucket, _, name = gcs_uri.removeprefix("gs://").partition("/")
    if not bucket or not name:
        return None
    return bucket, name


def lookup_paper_metadata(gcs_uri: str) -> dict[str, Any] | None:
    """Read the paper's DOI, title, year and first author off the object's metadata, if set.

    Best-effort: any failure is logged and the citation falls back to the file name.
    """
    parts = split_gcs_uri(gcs_uri)
    if parts is None:
        return None
    bucket, name = parts
    try:
        blob = storage_client().bucket(bucket).get_blob(name)
    except Exception as error:
        logger.warning(f"Paper metadata lookup failed for {gcs_uri}: {error}")
        return None
    metadata = (blob.metadata if blob is not None else None) or {}
    if not any(metadata.get(key) for key in METADATA_KEYS):
        return None
    first_author = metadata.get("first_author")
    return {
        "title": metadata.get("title"),
        "authors": [first_author] if first_author else [],
        "year": metadata.get("year"),
        "doi": metadata.get("doi"),
        "journal": None,
    }


def retrieve_rag_documentation(query: str) -> dict[str, Any]:
    """Search the configured Vertex AI RAG corpus for chunks relevant to the query.

    ALWAYS call this exactly once per user turn before writing an answer. Pass
    the user's literal question (or a minimally rephrased query).

    Args:
        query: The user's question, used verbatim as the retrieval query.

    Returns:
        A dict with one of two shapes:
          - {"chunks": [...]}        when the corpus has matching content
          - {"chunks": [], "empty": True}  when nothing matches
        Each chunk has: index (int, 1-based), text (str), source_uri (str),
        source_display_name (str), score (float), and, when the object carries
        paper metadata, title (str), authors (list[str]), year (str), doi (str).
    """
    rag_corpus = os.environ.get("RAG_CORPUS")
    if not rag_corpus:
        raise RuntimeError("RAG_CORPUS env var must be set to a full corpus resource path")

    response = rag.retrieval_query(
        text=query,
        rag_resources=[rag.RagResource(rag_corpus=rag_corpus)],
        similarity_top_k=int(os.environ.get("AGENT_TOP_K", "10")),
        vector_distance_threshold=float(os.environ.get("AGENT_DISTANCE_THRESHOLD", "0.6")),
    )

    contexts = list(response.contexts.contexts) if response.contexts else []
    if not contexts:
        return {"chunks": [], "empty": True}

    paper_metadata_cache: dict[str, dict[str, Any] | None] = {}
    chunks: list[dict[str, Any]] = []
    for i, c in enumerate(contexts):
        if c.source_uri not in paper_metadata_cache:
            paper_metadata_cache[c.source_uri] = lookup_paper_metadata(c.source_uri)
        paper = paper_metadata_cache[c.source_uri]

        chunk: dict[str, Any] = {
            "index": i + 1,
            "text": c.text,
            "source_uri": c.source_uri,
            "source_display_name": c.source_display_name,
            "score": c.score,
        }
        if paper:
            chunk.update(paper)
        chunks.append(chunk)

    return {"chunks": chunks}
