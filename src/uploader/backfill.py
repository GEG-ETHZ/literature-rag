"""Fill in ``first_author`` and ``year`` on objects already in the bucket, from Crossref or DataCite.

Only the object's custom metadata changes: the PDF stays as it is, so the ingestion function (triggered on
``object.finalized``) does not fire and the corpus is untouched. The agent reads the metadata at query
time, so a patched object is cited with author and year from the next answer on. Existing values are
never overwritten, and every write is guarded by the metageneration that was read, so an object changed
in the meantime fails instead of being overwritten.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

import google.cloud.storage as storage

from uploader.crossref import Record

BACKFILL_KEYS = ("first_author", "year")


@dataclass(frozen=True)
class StoredObject:
    """A PDF in the bucket with the metadata and metageneration read at listing time."""

    name: str
    metageneration: int
    metadata: Mapping[str, str]


class BackfillAction(Enum):
    """What happened to one object that lacks author or year."""

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
        """Add ``fields`` to the object's metadata if it is still at ``metageneration``."""
        ...


def missing_fields(metadata: Mapping[str, str]) -> tuple[str, ...]:
    """Return the backfill keys that are absent or empty in ``metadata``."""
    return tuple(key for key in BACKFILL_KEYS if not metadata.get(key))


def patch_for(metadata: Mapping[str, str], record: Record) -> dict[str, str]:
    """Return the missing fields that ``record`` can supply, as strings; never an existing key."""
    values = {"first_author": record.first_author, "year": str(record.year) if record.year else None}
    return {key: str(values[key]) for key in missing_fields(metadata) if values[key]}


def backfill_one(
    obj: StoredObject, lookup: Callable[[str], Record | None], store: MetadataStore, apply: bool
) -> BackfillRow:
    """Decide and, if ``apply``, patch one object that lacks author or year."""
    doi = obj.metadata.get("doi", "")
    if not doi:
        return BackfillRow(obj.name, "-", BackfillAction.NO_DOI)
    record = lookup(doi)
    if record is None:
        return BackfillRow(obj.name, doi, BackfillAction.NOT_FOUND, reason="neither Crossref nor DataCite")
    fields = patch_for(obj.metadata, record)
    if not fields:
        return BackfillRow(obj.name, doi, BackfillAction.NOTHING_TO_ADD, reason="registry has no author/year")
    if not apply:
        return BackfillRow(obj.name, doi, BackfillAction.WOULD_PATCH, fields)
    try:
        store.patch(obj.name, fields, obj.metageneration)
    except Exception as error:  # noqa: BLE001  any API error: report this object, keep going
        return BackfillRow(obj.name, doi, BackfillAction.FAILED, fields, f"{type(error).__name__}: {error}")
    return BackfillRow(obj.name, doi, BackfillAction.PATCHED, fields)


def backfill(store: MetadataStore, lookup: Callable[[str], Record | None], apply: bool) -> list[BackfillRow]:
    """Return one row per object that lacks author or year; complete objects are left out."""
    incomplete = [obj for obj in store.list_objects() if missing_fields(obj.metadata)]
    return [backfill_one(obj, lookup, store, apply) for obj in incomplete]


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
