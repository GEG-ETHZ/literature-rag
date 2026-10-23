from pathlib import Path
from unittest.mock import MagicMock

from uploader.bucket import GcsStore, local_md5


def blob(name: str, md5: str, metadata: dict[str, str] | None = None) -> MagicMock:
    b = MagicMock()
    b.name = name
    b.md5_hash = md5
    b.metadata = metadata
    return b


def test_local_md5_matches_gcs_base64_format(tmp_path: Path) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello")
    assert local_md5(f) == "XUFAKrxLKna5cZ2REBfFkg=="


def test_state_lists_pdf_names_and_md5s() -> None:
    client = MagicMock()
    client.list_blobs.return_value = [blob("a.pdf", "m1"), blob("notes.txt", "m2"), blob("b.pdf", "m3")]
    store = GcsStore(client=client, bucket_name="bkt")
    state = store.state()
    assert state.names == frozenset({"a.pdf", "b.pdf"})
    assert state.md5_to_name == {"m1": "a.pdf", "m3": "b.pdf"}


def test_upload_sets_metadata_and_uploads_file(tmp_path: Path) -> None:
    f = tmp_path / "p.pdf"
    f.write_bytes(b"%PDF")
    client = MagicMock()
    store = GcsStore(client=client, bucket_name="bkt")
    store.upload(f, "10.1_x.pdf", {"doi": "10.1/x"})
    target = client.bucket.return_value.blob.return_value
    client.bucket.assert_called_with("bkt")
    client.bucket.return_value.blob.assert_called_with("10.1_x.pdf")
    assert target.metadata == {"doi": "10.1/x"}
    target.upload_from_filename.assert_called_once()
    assert target.upload_from_filename.call_args.args == (str(f),)


def test_upload_uses_long_timeout_for_large_pdfs(tmp_path: Path) -> None:
    f = tmp_path / "p.pdf"
    f.write_bytes(b"%PDF")
    client = MagicMock()
    GcsStore(client=client, bucket_name="bkt").upload(f, "x.pdf", {})
    kwargs = client.bucket.return_value.blob.return_value.upload_from_filename.call_args.kwargs
    assert kwargs["timeout"] >= 600
