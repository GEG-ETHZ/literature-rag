"""Google Cloud Storage access, kept thin so the decision logic stays testable without the cloud."""

import base64
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import google.cloud.storage as storage

from uploader.plan import BucketState

PDF_CONTENT_TYPE = "application/pdf"
# Per-request timeout in seconds. The library default (60 s) is too short for a 30 MB PDF on a slow uplink.
UPLOAD_TIMEOUT_SECONDS = 900


class ObjectStore(Protocol):
    """What the CLI needs from a bucket."""

    def state(self) -> BucketState:
        """Return names and content hashes of the PDFs in the bucket."""
        ...

    def upload(self, path: Path, name: str, metadata: Mapping[str, str]) -> None:
        """Store ``path`` as ``name`` with ``metadata`` attached."""
        ...


def local_md5(path: Path) -> str:
    """Return the base64 MD5 of ``path``, the format GCS reports in ``md5_hash``."""
    digest = hashlib.md5(path.read_bytes(), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode("ascii")


class GcsStore:
    """An ``ObjectStore`` backed by one GCS bucket."""

    def __init__(self, client: storage.Client, bucket_name: str) -> None:
        """Wrap ``bucket_name`` on ``client``."""
        self.client = client
        self.bucket_name = bucket_name

    def state(self) -> BucketState:
        """List every ``.pdf`` object once; one request per page of 1000 objects."""
        blobs = [b for b in self.client.list_blobs(self.bucket_name) if b.name.lower().endswith(".pdf")]
        return BucketState(
            names=frozenset(b.name for b in blobs),
            md5_to_name={b.md5_hash: b.name for b in blobs if b.md5_hash},
        )

    def upload(self, path: Path, name: str, metadata: Mapping[str, str]) -> None:
        """Upload ``path`` as ``name`` with custom metadata; overwrites an existing object of that name."""
        blob = self.client.bucket(self.bucket_name).blob(name)
        blob.metadata = dict(metadata)
        blob.upload_from_filename(str(path), content_type=PDF_CONTENT_TYPE, timeout=UPLOAD_TIMEOUT_SECONDS)


def gcs_store(project: str, bucket_name: str) -> GcsStore:
    """Return a store on ``bucket_name`` using Application Default Credentials."""
    return GcsStore(client=storage.Client(project=project), bucket_name=bucket_name)


def download_pdfs(client: storage.Client, bucket_name: str, dest: Path) -> list[Path]:
    """Download every ``.pdf`` object of ``bucket_name`` into ``dest`` and return the local paths."""
    paths: list[Path] = []
    for blob in client.list_blobs(bucket_name):
        if not blob.name.lower().endswith(".pdf"):
            continue
        target = dest / Path(blob.name).name
        blob.download_to_filename(str(target))
        paths.append(target)
    return paths
