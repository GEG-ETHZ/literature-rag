import httpx

from uploader.crossref import doi_resolves, fetch_record


def client_returning(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_fetch_record_extracts_title_year_and_first_author() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works/10.1/abc"
        body = {
            "message": {
                "title": ["Great Paper"],
                "issued": {"date-parts": [[2024, 3]]},
                "author": [{"family": "Doe", "given": "J"}, {"family": "Roe"}],
            }
        }
        return httpx.Response(200, json=body)

    record = fetch_record("10.1/abc", client_returning(handler))
    assert record is not None
    assert (record.title, record.year, record.first_author) == ("Great Paper", 2024, "Doe")


def test_fetch_record_returns_none_on_404() -> None:
    record = fetch_record("10.1/missing", client_returning(lambda _r: httpx.Response(404)))
    assert record is None


def test_doi_resolves_true_for_redirect_and_false_for_404() -> None:
    assert doi_resolves("10.1/abc", client_returning(lambda _r: httpx.Response(302))) is True
    assert doi_resolves("10.1/abc", client_returning(lambda _r: httpx.Response(404))) is False


def search_handler(found_title: str) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert "query.bibliographic" in dict(request.url.params)
        items = [{"DOI": "10.1130/G37349.1", "title": [found_title], "author": [{"family": "Tutolo"}]}]
        return httpx.Response(200, json={"message": {"items": items}})

    return handler


def test_search_doi_by_title_accepts_close_match() -> None:
    from uploader.crossref import search_doi_by_title

    title = "Nanoscale constraints on porosity generation and fluid flow during serpentinization"
    client = client_returning(search_handler(title.upper()))
    assert search_doi_by_title(title, "Benjamin M. Tutolo, David Mildner", client) == "10.1130/g37349.1"


def test_search_doi_by_title_rejects_weak_match() -> None:
    from uploader.crossref import search_doi_by_title

    client = client_returning(search_handler("Something else entirely about basalt"))
    assert search_doi_by_title("Nanoscale constraints on porosity generation", "Tutolo", client) is None


def test_search_doi_by_title_rejects_match_whose_author_is_absent_from_text() -> None:
    from uploader.crossref import search_doi_by_title

    title = "Code development for modeling induced seismicity"
    client = client_returning(search_handler(title))
    assert search_doi_by_title(title, "LA-UR-20-20362 Birdsell, Saar", client) is None
