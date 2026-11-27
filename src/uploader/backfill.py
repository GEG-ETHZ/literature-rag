"""Fill in ``first_author`` and ``year`` on objects already in the bucket, and correct their titles.

Only the object's custom metadata changes: the PDF stays as it is, so the ingestion function (triggered on
``object.finalized``) does not fire and the corpus is untouched. The agent reads the metadata at query
time, so a patched object is cited with author and year from the next answer on. Author and year are
only ever added, never overwritten, and every write is guarded by the metageneration that was read, so
an object changed in the meantime fails instead of being overwritten.

Two things are opt-in. ``fix_titles`` replaces the title of a paper that has a DOI with the registry's
title when the two differ: titles read from a PDF's own metadata are sometimes a template placeholder,
another paper's title or cut off. ``manual`` supplies author and year for papers without a DOI from a
reviewed CSV (``docs/no-doi-metadata.csv``); it never sets a title.

The year in a migrated file's name (``2018_krietsch_...pdf``) comes from the GEG publication list and
wins over the registry: DataCite gives the Research Collection availability year or the arXiv preprint
year, which can be one or two years off the published paper's year.
"""

import csv
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Protocol

import google.cloud.storage as storage

from uploader.crossref import Record

BACKFILL_KEYS = ("first_author", "year")
FILENAME_YEAR = re.compile(r"^(\d{4})_")
MANUAL_COLUMNS = ("object", "first_author", "year")
MANUAL_YEAR = re.compile(r"^\d{4}$")
OLD_TITLE_PREVIEW_CHARS = 80


@dataclass(frozen=True)
class StoredObject:
    """A PDF in the bucket with the metadata and metageneration read at listing time."""

    name: str
    metageneration: int
    metadata: Mapping[str, str]


class BackfillAction(Enum):
    """What happened to one object that lacks author or year, or whose title differs from the registry."""

    WOULD_PATCH = "would patch"
    PATCHED = "patched"
    NO_DOI = "no doi"
    NOT_FOUND = "not found"
    NOTHING_TO_ADD = "nothing to add"
    FAILED = "failed"


@dataclass(frozen=True)
class BackfillRow:
    """One line of the report."""

    name: str
    doi: str
    action: BackfillAction
    fields: Mapping[str, str] = field(default_factory=dict)
    reason: str = ""


class MetadataStore(Protocol):
    """What the backfill needs from a bucket."""

    def list_objects(self) -> list[StoredObject]:
        """Return every PDF with its metadata and metageneration."""
        ...

    def patch(self, name: str, fields: Mapping[str, str], metageneration: int) -> None:
        """Set ``fields`` in the object's metadata if it is still at ``metageneration``."""
        ...


def missing_fields(metadata: Mapping[str, str]) -> tuple[str, ...]:
    """Return the backfill keys that are absent or empty in ``metadata``."""
    return tuple(key for key in BACKFILL_KEYS if not metadata.get(key))


def patch_for(metadata: Mapping[str, str], record: Record) -> dict[str, str]:
    """Return the missing fields that ``record`` can supply, as strings; never an existing key."""
    values = {"first_author": record.first_author, "year": str(record.year) if record.year else None}
    return {key: str(values[key]) for key in missing_fields(metadata) if values[key]}


def filename_year(metadata: Mapping[str, str]) -> str | None:
    """Return the leading ``YYYY_`` year of the original file name (October 2026 migration names)."""
    match = FILENAME_YEAR.match(metadata.get("original_filename", ""))
    return match.group(1) if match else None


def with_filename_year(metadata: Mapping[str, str], record: Record) -> tuple[Record, str]:
    """Return ``record`` with the file name's year, if any, and a note when the registry disagrees."""
    year = filename_year(metadata)
    if year is None:
        return record, ""
    note = (
        f"year from filename; registry says {record.year}" if record.year and str(record.year) != year else ""
    )
    return replace(record, year=int(year)), note


def title_fix(metadata: Mapping[str, str], record: Record) -> dict[str, str]:
    """Return the registry's title when it differs from the stored one, else nothing."""
    if not record.title or record.title == metadata.get("title"):
        return {}
    return {"title": record.title}


def old_title_note(metadata: Mapping[str, str]) -> str:
    """Return a one-line reminder of the title that is being replaced."""
    old = " ".join(metadata.get("title", "").split())
    return f"title was: {old[:OLD_TITLE_PREVIEW_CHARS]}"


def load_manual(path: Path) -> dict[str, Record]:
    """Read author and year for papers without a DOI from a CSV with ``object,first_author,year`` columns.

    Raises:
        ValueError: A column is missing, or a row has no object, no author or a year that is not ``YYYY``.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        absent = [column for column in MANUAL_COLUMNS if column not in (reader.fieldnames or [])]
        if absent:
            raise ValueError(f"{path.name}: missing columns {absent}; expected {list(MANUAL_COLUMNS)}")
        rows = list(reader)
    records: dict[str, Record] = {}
    for line, row in enumerate(rows, start=2):
        name, author, year = (row[column].strip() for column in MANUAL_COLUMNS)
        if not name or not author:
            raise ValueError(f"{path.name}, line {line}: object and first_author must not be empty")
        if not MANUAL_YEAR.match(year):
            raise ValueError(f"{path.name}, line {line}: year must be four digits, got {year!r}")
        records[name] = Record(title=None, year=int(year), first_author=author)
    return records


def decide(
    obj: StoredObject,
    lookup: Callable[[str], Record | None],
    fix_titles: bool,
    manual: Mapping[str, Record],
) -> BackfillRow | None:
    """Return what to do with ``obj``, or ``None`` when it is complete and its title needs no change."""
    doi = obj.metadata.get("doi", "")
    if doi:
        found = lookup(doi)
        if found is None:
            reason = "neither Crossref nor DataCite answered; rerun"
            return BackfillRow(obj.name, doi, BackfillAction.NOT_FOUND, reason=reason)
        record, note = with_filename_year(obj.metadata, found)
    elif obj.name in manual:
        record, note = manual[obj.name], "from the manual file"
    else:
        return BackfillRow(obj.name, "-", BackfillAction.NO_DOI)
    new_title = title_fix(obj.metadata, record) if fix_titles and doi else {}
    fields = {**patch_for(obj.metadata, record), **new_title}
    if not fields:
        if not missing_fields(obj.metadata):
            return None
        reason = "registry has no author/year"
        return BackfillRow(obj.name, doi, BackfillAction.NOTHING_TO_ADD, reason=reason)
    notes = [note, old_title_note(obj.metadata) if new_title else ""]
    reason = "; ".join(n for n in notes if n)
    return BackfillRow(obj.name, doi or "-", BackfillAction.WOULD_PATCH, fields, reason)


def execute(row: BackfillRow, obj: StoredObject, store: MetadataStore) -> BackfillRow:
    """Write the planned fields of ``row``; a failure is reported for this object and the run goes on."""
    try:
        store.patch(obj.name, row.fields, obj.metageneration)
    except Exception as error:  # noqa: BLE001  any API error: report this object, keep going
        return replace(row, action=BackfillAction.FAILED, reason=f"{type(error).__name__}: {error}")
    return replace(row, action=BackfillAction.PATCHED)


def backfill(
    store: MetadataStore,
    lookup: Callable[[str], Record | None],
    apply: bool,
    fix_titles: bool = False,
    manual: Mapping[str, Record] | None = None,
) -> list[BackfillRow]:
    """Return one row per object that needs something; complete objects with a correct title are left out.

    Without ``fix_titles`` only objects that lack author or year are looked up.
    """
    rows: list[BackfillRow] = []
    for obj in store.list_objects():
        has_doi = bool(obj.metadata.get("doi"))
        if not missing_fields(obj.metadata) and not (fix_titles and has_doi):
            continue
        row = decide(obj, lookup, fix_titles, manual or {})
        if row is None:
            continue
        planned = row.action is BackfillAction.WOULD_PATCH
        rows.append(execute(row, obj, store) if apply and planned else row)
    return rows


class GcsMetadataStore:
    """A ``MetadataStore`` backed by one GCS bucket."""

    def __init__(self, client: storage.Client, bucket_name: str) -> None:
        """Wrap ``bucket_name`` on ``client``."""
        self.client = client
        self.bucket_name = bucket_name

    def list_objects(self) -> list[StoredObject]:
        """List every ``.pdf`` object with its custom metadata and metageneration."""
        return [
            StoredObject(name=b.name, metageneration=int(b.metageneration), metadata=dict(b.metadata or {}))
            for b in self.client.list_blobs(self.bucket_name)
            if b.name.lower().endswith(".pdf")
        ]

    def patch(self, name: str, fields: Mapping[str, str], metageneration: int) -> None:
        """Send only ``fields``; GCS merges them into the existing custom metadata."""
        if not fields:
            raise ValueError(f"{name}: refusing an empty metadata patch")
        blob = self.client.bucket(self.bucket_name).blob(name)
        blob.metadata = dict(fields)
        blob.patch(if_metageneration_match=metageneration)
