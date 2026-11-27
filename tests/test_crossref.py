import httpx
import pytest

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


def test_clean_title_strips_markup_and_collapses_whitespace() -> None:
    from uploader.crossref import clean_title

    raw = "Changes induced by reactive transport of\n   <scp>CO</scp>\n   <sub>2</sub>\n   ‐rich brine"
    assert clean_title(raw) == "Changes induced by reactive transport of CO2 ‐rich brine"
    assert clean_title("A &amp; B  study") == "A & B study"
    assert clean_title("Plain title") == "Plain title"
    assert clean_title(None) is None
    assert clean_title("  <i></i> ") is None


def test_fetch_record_returns_a_clean_title() -> None:
    body = {"message": {"title": ["Flow of CO\n   <sub>2</sub>\n   in rock"], "author": [{"family": "Doe"}]}}
    record = fetch_record("10.1/abc", client_returning(lambda _r: httpx.Response(200, json=body)))
    assert record is not None and record.title == "Flow of CO2 in rock"


CROSSREF_BODY = {
    "message": {"title": ["Paper"], "issued": {"date-parts": [[2020]]}, "author": [{"family": "Doe"}]}
}


def test_fetch_record_waits_and_retries_when_crossref_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:

    waits: list[float] = []
    monkeypatch.setattr("uploader.crossref.time.sleep", waits.append)
    answers = iter([httpx.Response(429), httpx.Response(429), httpx.Response(200, json=CROSSREF_BODY)])
    record = fetch_record("10.1/abc", client_returning(lambda _r: next(answers)))
    assert record is not None and record.first_author == "Doe"
    assert len(waits) == 2 and waits[1] > waits[0] > 0


def test_fetch_record_gives_up_after_repeated_rate_limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    from uploader import crossref

    calls: list[str] = []
    monkeypatch.setattr("uploader.crossref.time.sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429)

    assert fetch_record("10.1/abc", client_returning(handler)) is None
    assert len(calls) == crossref.RATE_LIMIT_ATTEMPTS


def test_a_404_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:

    calls: list[str] = []
    monkeypatch.setattr("uploader.crossref.time.sleep", lambda _s: pytest.fail("must not wait on a 404"))

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(404)

    assert fetch_record("10.1/missing", client_returning(handler)) is None
    assert len(calls) == 1
