"""Find and normalise a DOI from PDF metadata or text."""

import re
from collections.abc import Mapping

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
ARXIV_PATTERN = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
ARXIV_DOI_PREFIX = "10.48550/arxiv."
TRAILING_PUNCTUATION = ".,;:)]}"


def clean_doi(raw: str) -> str:
    """Return the bare, lower-cased DOI inside ``raw``.

    Strips ``https://doi.org/`` and ``doi:`` prefixes and trailing punctuation that regexes drag along from
    running text. DOIs are case-insensitive by specification, so lower-casing is lossless.
    """
    match = DOI_PATTERN.search(raw)
    candidate = match.group(0) if match else raw.strip()
    return candidate.rstrip(TRAILING_PUNCTUATION).lower()


def find_doi(metadata: Mapping[str, str], text: str) -> str | None:
    """Return the most trustworthy DOI found, or ``None``.

    Order of trust: metadata values whose key mentions ``doi``, then any other metadata value, then the
    extracted page text, then an arXiv identifier in the text. Metadata is set by the publisher; page text
    may contain cited DOIs of other works.
    """
    keyed = [v for k, v in metadata.items() if "doi" in k.lower()]
    others = [v for k, v in metadata.items() if "doi" not in k.lower()]
    for source in (*keyed, *others, text):
        match = DOI_PATTERN.search(source or "")
        if match:
            return clean_doi(match.group(0))
    return arxiv_doi(text)


def arxiv_doi(text: str) -> str | None:
    """Return the DOI arXiv registers for every preprint, ``10.48550/arXiv.<id>``, if the stamp is present."""
    match = ARXIV_PATTERN.search(text or "")
    return f"{ARXIV_DOI_PREFIX}{match.group(1)}" if match else None
