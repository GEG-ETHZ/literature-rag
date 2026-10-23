from uploader.doi import clean_doi, find_doi


def test_clean_doi_strips_url_prefix_and_lowercases() -> None:
    assert clean_doi("https://doi.org/10.1016/J.CESYS.2022.100086") == "10.1016/j.cesys.2022.100086"


def test_clean_doi_strips_doi_label_and_trailing_punctuation() -> None:
    assert clean_doi("doi:10.1007/s10596-019-09926-4.") == "10.1007/s10596-019-09926-4"
    assert clean_doi("DOI 10.3390/en14196122);") == "10.3390/en14196122"


def test_find_doi_prefers_metadata_key_named_doi() -> None:
    metadata = {"doi": "10.1016/j.geothermics.2020.101865", "subject": "10.9999/wrong"}
    assert find_doi(metadata, "text with 10.8888/also-wrong") == "10.1016/j.geothermics.2020.101865"


def test_find_doi_falls_back_to_any_metadata_value() -> None:
    metadata = {"subject": "Journal, doi:10.1186/s40517-020-00172-x"}
    assert find_doi(metadata, "") == "10.1186/s40517-020-00172-x"


def test_find_doi_falls_back_to_text() -> None:
    text = "Solid Earth, 11, 1699–1729, 2020\nhttps://doi.org/10.5194/se-11-1699-2020\n© Author(s) 2020."
    assert find_doi({}, text) == "10.5194/se-11-1699-2020"


def test_find_doi_returns_none_when_absent() -> None:
    assert find_doi({"title": "No identifiers here"}, "plain text 10.5 / nothing") is None


def test_find_doi_uses_arxiv_identifier_when_no_doi_present() -> None:
    text = "arXiv:1801.08321v1 [physics.geo-ph] 25 Jan 2018\nEstimating fluid flow rates through fractures"
    assert find_doi({}, text) == "10.48550/arxiv.1801.08321"


def test_find_doi_prefers_real_doi_over_arxiv_identifier() -> None:
    text = "arXiv:1801.08321v1\nPublished: https://doi.org/10.1016/j.advwatres.2018.01.001"
    assert find_doi({}, text) == "10.1016/j.advwatres.2018.01.001"
