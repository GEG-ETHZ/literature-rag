from unittest.mock import MagicMock

import pytest

from agent.tools import (
    lookup_paper_metadata,
    retrieve_rag_documentation,
    split_gcs_uri,
    storage_client,
)


@pytest.fixture(autouse=True)
def _clear_storage_client_cache():
    """The storage client is cached per process, so drop it around every test."""
    storage_client.cache_clear()
    yield
    storage_client.cache_clear()


def _make_context(text, source_uri, source_display_name, score):
    context = MagicMock()
    context.text = text
    context.source_uri = source_uri
    context.source_display_name = source_display_name
    context.score = score
    return context


def _blob_with(mocker, metadata):
    client = mocker.patch("agent.tools.storage.Client")
    blob = client.return_value.bucket.return_value.get_blob.return_value
    blob.metadata = metadata
    return client


def test_split_gcs_uri():
    assert split_gcs_uri("gs://bucket/dir/paper.pdf") == ("bucket", "dir/paper.pdf")
    assert split_gcs_uri("gs://bucket") is None
    assert split_gcs_uri("https://x/y") is None
    assert split_gcs_uri("") is None


def test_lookup_paper_metadata_reads_the_object_metadata(mocker):
    client = _blob_with(
        mocker,
        {
            "doi": "10.3390/en14164717",
            "title": "Geothermal Energy Potential",
            "year": "2021",
            "first_author": "Ezzat",
            "original_filename": "paper.pdf",
        },
    )

    metadata = lookup_paper_metadata("gs://bucket/10.3390_en14164717.pdf")

    assert metadata == {
        "title": "Geothermal Energy Potential",
        "authors": ["Ezzat"],
        "year": "2021",
        "doi": "10.3390/en14164717",
        "journal": None,
    }
    client.return_value.bucket.assert_called_once_with("bucket")
    client.return_value.bucket.return_value.get_blob.assert_called_once_with("10.3390_en14164717.pdf")


def test_lookup_paper_metadata_returns_none_without_paper_fields(mocker):
    _blob_with(mocker, {"uploaded_by": "someone"})

    assert lookup_paper_metadata("gs://bucket/paper.pdf") is None


def test_lookup_paper_metadata_returns_none_when_object_is_missing(mocker):
    client = mocker.patch("agent.tools.storage.Client")
    client.return_value.bucket.return_value.get_blob.return_value = None

    assert lookup_paper_metadata("gs://bucket/paper.pdf") is None


def test_lookup_paper_metadata_returns_none_on_error(mocker):
    mocker.patch("agent.tools.storage.Client", side_effect=Exception("unavailable"))

    assert lookup_paper_metadata("gs://bucket/paper.pdf") is None


def test_lookup_paper_metadata_returns_none_for_bad_uri():
    assert lookup_paper_metadata("") is None


def test_retrieve_rag_documentation_merges_paper_metadata_into_chunks(mocker):
    mocker.patch.dict("os.environ", {"RAG_CORPUS": "projects/p/locations/l/ragCorpora/123"}, clear=False)

    contexts = [
        _make_context("chunk one text", "gs://bucket/paper.pdf", "paper.pdf", 0.9),
        _make_context("chunk two text", "gs://bucket/paper.pdf", "paper.pdf", 0.8),
        _make_context("chunk three text", "gs://bucket/other.pdf", "other.pdf", 0.7),
    ]
    mock_response = MagicMock()
    mock_response.contexts.contexts = contexts
    mocker.patch("agent.tools.rag.retrieval_query", return_value=mock_response)
    mocker.patch("agent.tools.rag.RagResource")

    paper_metadata = {
        "title": "Geothermal Energy Potential",
        "authors": ["Ezzat"],
        "year": "2021",
        "doi": "10.3390/en14164717",
        "journal": None,
    }
    mock_lookup = mocker.patch(
        "agent.tools.lookup_paper_metadata",
        side_effect=lambda uri: paper_metadata if uri == "gs://bucket/paper.pdf" else None,
    )

    result = retrieve_rag_documentation("what is geothermal energy")

    chunks = result["chunks"]
    assert len(chunks) == 3
    assert chunks[0]["title"] == "Geothermal Energy Potential"
    assert chunks[0]["authors"] == ["Ezzat"]
    assert chunks[0]["year"] == "2021"
    assert chunks[0]["doi"] == "10.3390/en14164717"
    assert chunks[1]["title"] == "Geothermal Energy Potential"
    assert "title" not in chunks[2]
    assert "authors" not in chunks[2]

    # Same source_uri looked up only once despite two chunks sharing it.
    assert mock_lookup.call_count == 2
    mock_lookup.assert_any_call("gs://bucket/paper.pdf")
    mock_lookup.assert_any_call("gs://bucket/other.pdf")


def test_retrieve_rag_documentation_returns_empty_when_no_contexts(mocker):
    mocker.patch.dict("os.environ", {"RAG_CORPUS": "projects/p/locations/l/ragCorpora/123"}, clear=False)

    mock_response = MagicMock()
    mock_response.contexts = None
    mocker.patch("agent.tools.rag.retrieval_query", return_value=mock_response)
    mocker.patch("agent.tools.rag.RagResource")
    mock_lookup = mocker.patch("agent.tools.lookup_paper_metadata")

    result = retrieve_rag_documentation("what is geothermal energy")

    assert result == {"chunks": [], "empty": True}
    mock_lookup.assert_not_called()


def test_retrieve_rag_documentation_requires_corpus(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)

    with pytest.raises(RuntimeError, match="RAG_CORPUS"):
        retrieve_rag_documentation("anything")
