"""Validate a DOI and fetch its bibliographic record from Crossref."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx

CROSSREF_WORKS = "https://api.crossref.org/works/"
DOI_RESOLVER = "https://doi.org/"
USER_AGENT = "rag-own-publications/0.1 (GEG ETH Zurich; mailto:geg-computing@ethz.ch)"
TIMEOUT_SECONDS = 15.0
TITLE_MATCH_THRESHOLD = 0.9


@dataclass(frozen=True)
class Record:
    """Bibliographic facts stored as object metadata next to the PDF."""

    title: str | None
    year: int | None
    first_author: str | None


def new_client() -> httpx.Client:
    """Return an HTTP client with the polite headers Crossref asks for."""
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS, follow_redirects=False)


def doi_resolves(doi: str, client: httpx.Client) -> bool:
    """Return whether doi.org knows ``doi``. A redirect counts as yes; a 4xx or 5xx as no."""
    try:
        response = client.head(f"{DOI_RESOLVER}{doi}")
    except httpx.HTTPError:
        return False
    return response.status_code < 400


def fetch_record(doi: str, client: httpx.Client) -> Record | None:
    """Return title, year and first author from Crossref, or ``None`` if the DOI is unknown there."""
    try:
        response = client.get(f"{CROSSREF_WORKS}{doi}")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    message: dict[str, Any] = response.json().get("message", {})
    titles = message.get("title") or [None]
    date_parts = (message.get("issued") or {}).get("date-parts") or [[None]]
    authors = message.get("author") or [{}]
    return Record(title=titles[0], year=date_parts[0][0], first_author=authors[0].get("family"))


def normalised(title: str) -> str:
    """Lower-case letters and digits only, so punctuation and casing do not affect the comparison."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def search_doi_by_title(title: str, text: str, client: httpx.Client) -> str | None:
    """Return the DOI of the Crossref work whose title matches ``title`` closely, else ``None``.

    Used for PDFs that carry no DOI themselves. The match must be near-exact (``TITLE_MATCH_THRESHOLD``)
    and the work's first author must appear in ``text`` (the PDF's leading pages), because Crossref always
    returns a best guess, however poor, and bare titles such as "Coversheet" collide.
    """
    try:
        response = client.get(CROSSREF_WORKS.rstrip("/"), params={"query.bibliographic": title, "rows": 1})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    items: list[dict[str, Any]] = response.json().get("message", {}).get("items", [])
    if not items or not items[0].get("title"):
        return None
    similarity = SequenceMatcher(None, normalised(title), normalised(items[0]["title"][0])).ratio()
    family = ((items[0].get("author") or [{}])[0].get("family") or "").strip()
    author_present = bool(family) and family.lower() in text.lower()
    return str(items[0]["DOI"]).lower() if similarity >= TITLE_MATCH_THRESHOLD and author_present else None
