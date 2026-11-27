from collections.abc import Mapping
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uploader.backfill import (
    BackfillAction,
    GcsMetadataStore,
    StoredObject,
    backfill,
    missing_fields,
    patch_for,
)
from uploader.crossref import Record

EZZAT = Record(title="Plasma-Pulse Geo-Drilling", year=2024, first_author="Ezzat")


def stored(name: str, metadata: dict[str, str], metageneration: int = 1) -> StoredObject:
    return StoredObject(name=name, metageneration=metageneration, metadata=metadata)


class FakeMetadataStore:
    def __init__(self, objects: list[StoredObject], fail_on: str | None = None) -> None:
        self.objects = objects
        self.fail_on = fail_on
        self.patches: list[tuple[str, dict[str, str], int]] = []

    def list_objects(self) -> list[StoredObject]:
        return self.objects

    def patch(self, name: str, fields: Mapping[str, str], metageneration: int) -> None:
        if name == self.fail_on:
            raise RuntimeError("412 Precondition Failed")
        self.patches.append((name, dict(fields), metageneration))


def lookup_from(records: dict[str, Record | None]) -> object:
    return lambda doi: records.get(doi)


def test_missing_fields_names_absent_and_empty_keys() -> None:
    assert missing_fields({"doi": "10.1/x", "year": ""}) == ("first_author", "year")
    assert missing_fields({"first_author": "Doe", "year": "2020"}) == ()


def test_patch_for_fills_only_missing_fields() -> None:
    assert patch_for({"doi": "d", "year": "2023"}, EZZAT) == {"first_author": "Ezzat"}
    assert patch_for({"doi": "d"}, EZZAT) == {"first_author": "Ezzat", "year": "2024"}


def test_patch_for_skips_fields_the_record_does_not_have() -> None:
    assert patch_for({"doi": "d"}, Record(title="T", year=2015, first_author=None)) == {"year": "2015"}
    assert patch_for({"doi": "d"}, Record(title="T", year=None, first_author=None)) == {}


def test_dry_run_reports_without_patching() -> None:
    store = FakeMetadataStore([stored("10.3929_x.pdf", {"doi": "10.3929/x"})])
    rows = backfill(store, lookup_from({"10.3929/x": EZZAT}), apply=False)  # type: ignore[arg-type]
    assert store.patches == []
    assert [(r.name, r.action, r.fields) for r in rows] == [
        ("10.3929_x.pdf", BackfillAction.WOULD_PATCH, {"first_author": "Ezzat", "year": "2024"})
    ]


def test_apply_patches_with_the_metageneration_it_read() -> None:
    store = FakeMetadataStore([stored("10.3929_x.pdf", {"doi": "10.3929/x"}, metageneration=7)])
    rows = backfill(store, lookup_from({"10.3929/x": EZZAT}), apply=True)  # type: ignore[arg-type]
    assert store.patches == [("10.3929_x.pdf", {"first_author": "Ezzat", "year": "2024"}, 7)]
    assert rows[0].action is BackfillAction.PATCHED


def test_complete_objects_and_objects_without_doi_are_not_looked_up() -> None:
    asked: list[str] = []

    def lookup(doi: str) -> Record | None:
        asked.append(doi)
        return EZZAT

    store = FakeMetadataStore(
        [
            stored("done.pdf", {"doi": "10.1/done", "first_author": "Doe", "year": "2020"}),
            stored("nodoi.pdf", {"title": "Report"}),
        ]
    )
    rows = backfill(store, lookup, apply=True)
    assert asked == []
    assert store.patches == []
    assert [r.action for r in rows] == [BackfillAction.NO_DOI]


def test_unknown_doi_and_empty_record_are_reported_not_patched() -> None:
    store = FakeMetadataStore([stored("a.pdf", {"doi": "10.1/a"}), stored("b.pdf", {"doi": "10.1/b"})])
    empty = Record(title=None, year=None, first_author=None)
    rows = backfill(store, lookup_from({"10.1/a": None, "10.1/b": empty}), apply=True)  # type: ignore[arg-type]
    assert store.patches == []
    assert [r.action for r in rows] == [BackfillAction.NOT_FOUND, BackfillAction.NOTHING_TO_ADD]


def test_failed_patch_is_reported_and_the_run_continues() -> None:
    objects = [stored("a.pdf", {"doi": "10.1/a"}), stored("b.pdf", {"doi": "10.1/b"})]
    store = FakeMetadataStore(objects, fail_on="a.pdf")
    rows = backfill(store, lookup_from({"10.1/a": EZZAT, "10.1/b": EZZAT}), apply=True)  # type: ignore[arg-type]
    assert [r.action for r in rows] == [BackfillAction.FAILED, BackfillAction.PATCHED]
    assert "412" in rows[0].reason
    assert [p[0] for p in store.patches] == ["b.pdf"]


def gcs_blob(name: str, metadata: dict[str, str] | None, metageneration: int = 3) -> MagicMock:
    b = MagicMock()
    b.name = name
    b.metadata = metadata
    b.metageneration = metageneration
    return b


def test_gcs_store_lists_pdfs_with_metadata_and_metageneration() -> None:
    client = MagicMock()
    client.list_blobs.return_value = [
        gcs_blob("a.pdf", {"doi": "d"}),
        gcs_blob("x.txt", {}),
        gcs_blob("b.pdf", None),
    ]
    objects = GcsMetadataStore(client=client, bucket_name="bkt").list_objects()
    assert objects == [
        StoredObject(name="a.pdf", metageneration=3, metadata={"doi": "d"}),
        StoredObject(name="b.pdf", metageneration=3, metadata={}),
    ]


def test_gcs_store_patches_only_the_given_keys_guarded_by_metageneration() -> None:
    client = MagicMock()
    GcsMetadataStore(client=client, bucket_name="bkt").patch("a.pdf", {"year": "2024"}, metageneration=5)
    client.bucket.assert_called_with("bkt")
    target = client.bucket.return_value.blob.return_value
    client.bucket.return_value.blob.assert_called_with("a.pdf")
    assert target.metadata == {"year": "2024"}
    target.patch.assert_called_once_with(if_metageneration_match=5)


def test_gcs_store_rejects_an_empty_patch() -> None:
    with pytest.raises(ValueError, match="empty"):
        GcsMetadataStore(client=MagicMock(), bucket_name="bkt").patch("a.pdf", {}, metageneration=1)


def test_filename_year_reads_the_leading_year_of_the_original_filename() -> None:
    from uploader.backfill import filename_year

    assert filename_year({"original_filename": "2018_krietsch_stress-measurements.pdf"}) == "2018"
    assert filename_year({"original_filename": "Water Resources Research - 2020 - Lima.pdf"}) is None
    assert filename_year({}) is None


def test_filename_year_wins_over_the_registry_year_and_the_conflict_is_reported() -> None:
    metadata = {"doi": "10.3929/k", "original_filename": "2018_krietsch_stress.pdf"}
    store = FakeMetadataStore([stored("10.3929_k.pdf", metadata)])
    krietsch = Record(title="Stress", year=2019, first_author="Krietsch")
    rows = backfill(store, lookup_from({"10.3929/k": krietsch}), apply=False)  # type: ignore[arg-type]
    assert rows[0].fields == {"first_author": "Krietsch", "year": "2018"}
    assert rows[0].reason == "year from filename; registry says 2019"


def test_matching_filename_year_is_not_reported_as_a_conflict() -> None:
    metadata = {"doi": "10.3929/e", "original_filename": "2024_ezzat_thesis.pdf"}
    store = FakeMetadataStore([stored("10.3929_e.pdf", metadata)])
    rows = backfill(store, lookup_from({"10.3929/e": EZZAT}), apply=False)  # type: ignore[arg-type]
    assert (rows[0].fields["year"], rows[0].reason) == ("2024", "")


ROSSI = Record(title="Advanced drilling technologies", year=2020, first_author="Rossi")
COMPLETE = {"doi": "10.3929/r", "first_author": "Rossi", "year": "2020"}


def test_titles_are_left_alone_unless_asked() -> None:
    store = FakeMetadataStore(
        [stored("r.pdf", {**COMPLETE, "title": "Paper Title (use style: paper title)"})]
    )
    assert backfill(store, lookup_from({"10.3929/r": ROSSI}), apply=True) == []  # type: ignore[arg-type]
    assert store.patches == []


def test_fix_titles_replaces_a_title_that_differs_from_the_registry() -> None:
    store = FakeMetadataStore(
        [stored("r.pdf", {**COMPLETE, "title": "Paper Title (use style: paper title)"})]
    )
    rows = backfill(store, lookup_from({"10.3929/r": ROSSI}), apply=True, fix_titles=True)  # type: ignore[arg-type]
    assert store.patches == [("r.pdf", {"title": "Advanced drilling technologies"}, 1)]
    assert rows[0].action is BackfillAction.PATCHED
    assert rows[0].reason == "title was: Paper Title (use style: paper title)"


def test_fix_titles_skips_matching_titles_and_records_without_a_title() -> None:
    objects = [
        stored("same.pdf", {**COMPLETE, "title": "Advanced drilling technologies"}),
        stored("untitled.pdf", {"doi": "10.1/u", "first_author": "Doe", "year": "2020", "title": "Kept"}),
    ]
    store = FakeMetadataStore(objects)
    untitled = Record(title=None, year=2020, first_author="Doe")
    lookup = lookup_from({"10.3929/r": ROSSI, "10.1/u": untitled})
    assert backfill(store, lookup, apply=True, fix_titles=True) == []  # type: ignore[arg-type]
    assert store.patches == []


def test_fix_titles_reports_a_failed_lookup_for_a_complete_object() -> None:
    store = FakeMetadataStore([stored("r.pdf", {**COMPLETE, "title": "T"})])
    rows = backfill(store, lookup_from({}), apply=True, fix_titles=True)  # type: ignore[arg-type]
    assert [r.action for r in rows] == [BackfillAction.NOT_FOUND]


def test_manual_record_fills_an_object_without_doi_and_never_its_title() -> None:
    store = FakeMetadataStore([stored("hydro.pdf", {"title": "Hydro-Mechanically Coupled Flow"})])
    manual = {"hydro.pdf": Record(title=None, year=2016, first_author="Vogler")}
    rows = backfill(store, lookup_from({}), apply=True, fix_titles=True, manual=manual)  # type: ignore[arg-type]
    assert store.patches == [("hydro.pdf", {"first_author": "Vogler", "year": "2016"}, 1)]
    assert rows[0].action is BackfillAction.PATCHED


def test_manual_record_is_ignored_for_an_object_that_has_a_doi() -> None:
    store = FakeMetadataStore([stored("x.pdf", {"doi": "10.3929/x"})])
    manual = {"x.pdf": Record(title=None, year=1999, first_author="Wrong")}
    rows = backfill(store, lookup_from({"10.3929/x": EZZAT}), apply=False, manual=manual)  # type: ignore[arg-type]
    assert rows[0].fields == {"first_author": "Ezzat", "year": "2024"}


def test_load_manual_reads_rows_and_rejects_bad_ones(tmp_path: Path) -> None:
    from uploader.backfill import load_manual

    good = tmp_path / "good.csv"
    good.write_text("object,first_author,year,evidence\nhydro.pdf,Vogler,2016,first page\n", encoding="utf-8")
    assert load_manual(good) == {"hydro.pdf": Record(title=None, year=2016, first_author="Vogler")}

    bad_year = tmp_path / "bad_year.csv"
    bad_year.write_text("object,first_author,year,evidence\nhydro.pdf,Vogler,16,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="year"):
        load_manual(bad_year)

    no_author = tmp_path / "no_author.csv"
    no_author.write_text("object,first_author,year,evidence\nhydro.pdf,,2016,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="first_author"):
        load_manual(no_author)

    missing_column = tmp_path / "missing.csv"
    missing_column.write_text("object,year\nhydro.pdf,2016\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        load_manual(missing_column)
