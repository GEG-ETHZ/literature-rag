from collections.abc import Mapping
from pathlib import Path

import pymupdf
import pytest

from uploader import cli
from uploader.plan import BucketState


class FakeStore:
    def __init__(self, state: BucketState) -> None:
        self.current = state
        self.uploads: list[tuple[str, dict[str, str]]] = []

    def state(self) -> BucketState:
        return self.current

    def upload(self, path: Path, name: str, metadata: Mapping[str, str]) -> None:
        self.uploads.append((name, {**metadata, "_path": path.name}))


def write_pdf(path: Path, doi: str | None, heading: str = "Some Heading Text") -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), heading, fontsize=20)
    if doi:
        page.insert_text((72, 200), f"https://doi.org/{doi}", fontsize=10)
    doc.save(str(path))


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    write_pdf(tmp_path / "2020_A.pdf", "10.1000/one")
    write_pdf(tmp_path / "2021_B.pdf", "10.1000/two")
    write_pdf(tmp_path / "2022_C.pdf", None)
    return tmp_path


def test_dry_run_reports_without_uploading(folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = FakeStore(BucketState(names=frozenset(), md5_to_name={}))
    code = cli.run(["migrate", str(folder), "--dry-run", "--offline"], store=store)
    out = capsys.readouterr().out
    assert code == 0
    assert store.uploads == []
    assert "10.1000_one.pdf" in out and "10.1000_two.pdf" in out and "some-heading-text.pdf" in out


def test_upload_writes_metadata_and_skips_duplicates_within_batch(folder: Path) -> None:
    store = FakeStore(BucketState(names=frozenset(), md5_to_name={}))
    duplicate = folder / "copy_of_A.pdf"
    duplicate.write_bytes((folder / "2020_A.pdf").read_bytes())
    code = cli.run(["migrate", str(folder), "--offline"], store=store)
    names = [name for name, _ in store.uploads]
    assert code == 0
    assert names.count("10.1000_one.pdf") == 1
    assert store.uploads[0][1]["doi"] == "10.1000/one"
    assert store.uploads[0][1]["original_filename"] == "2020_A.pdf"


def test_needs_override_exits_nonzero(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf))
    store = FakeStore(BucketState(names=frozenset(), md5_to_name={}))
    assert cli.run(["upload", str(pdf), "--offline"], store=store) == 1
    assert store.uploads == []


def test_doi_override_names_file(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf))
    store = FakeStore(BucketState(names=frozenset(), md5_to_name={}))
    assert cli.run(["upload", str(pdf), "--offline", "--doi", "10.5555/forced"], store=store) == 0
    assert store.uploads[0][0] == "10.5555_forced.pdf"


class FlakyStore(FakeStore):
    def upload(self, path: Path, name: str, metadata: Mapping[str, str]) -> None:
        if path.name == "2021_B.pdf":
            raise TimeoutError("The write operation timed out")
        super().upload(path, name, metadata)


def test_failed_upload_is_reported_and_the_run_continues(
    folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = FlakyStore(BucketState(names=frozenset(), md5_to_name={}))
    code = cli.run(["migrate", str(folder), "--offline"], store=store)
    names = [name for name, _ in store.uploads]
    assert code == 1
    assert "10.1000_one.pdf" in names and "some-heading-text.pdf" in names
    assert "upload failed" in capsys.readouterr().out
