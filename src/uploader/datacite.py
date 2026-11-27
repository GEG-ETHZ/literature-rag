"""Fetch a bibliographic record from DataCite, the registry behind ETH Research Collection and arXiv DOIs.

Crossref answers 404 for DOIs registered with DataCite (``10.3929/...``, ``10.48550/arxiv...``), so
without this fallback those papers are stored without author and year and cited by title only.
"""

from typing import Any

import httpx

from uploader.crossref import Record, fetch_record

DATACITE_DOIS = "https://api.datacite.org/dois/"
DATACITE_PLACEHOLDER_PREFIXES = ("(:", ":")


def first_family_name(creators: list[dict[str, Any]]) -> str | None:
    """Return the first creator's family name, an organisation's name, or ``None`` for a placeholder.

    DataCite marks unknown values with codes such as ``(:unkn)`` or ``:unav``; those are not authors.
    """
    if not creators:
        return None
    creator = creators[0]
    name = str(creator.get("name") or "").strip()
    if name.startswith(DATACITE_PLACEHOLDER_PREFIXES):
        return None
    if creator.get("familyName"):
        return str(creator["familyName"]).strip()
    if creator.get("nameType") == "Organizational":
        return name or None
    return name.split(",")[0].strip() or None


def fetch_datacite_record(doi: str, client: httpx.Client) -> Record | None:
    """Return title, year and first author from DataCite, or ``None`` if the DOI is unknown there."""
    try:
        response = client.get(f"{DATACITE_DOIS}{doi}")
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    attributes: dict[str, Any] = response.json().get("data", {}).get("attributes", {})
    titles = attributes.get("titles") or [{}]
    year = attributes.get("publicationYear")
    return Record(
        title=titles[0].get("title"),
        year=int(year) if year else None,
        first_author=first_family_name(attributes.get("creators") or []),
    )


def lookup_record(doi: str, client: httpx.Client) -> Record | None:
    """Return the record from Crossref, else from DataCite, else ``None``."""
    return fetch_record(doi, client) or fetch_datacite_record(doi, client)
