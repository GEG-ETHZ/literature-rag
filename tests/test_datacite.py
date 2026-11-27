import httpx

from uploader.crossref import Record
from uploader.datacite import fetch_datacite_record, first_family_name, lookup_record


def client_returning(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def datacite_body(creators: list[dict[str, str]], year: int | None = 2024) -> dict[str, object]:
    attributes = {"titles": [{"title": "A Thesis"}], "publicationYear": year, "creators": creators}
    return {"data": {"attributes": attributes}}


def test_fetch_datacite_record_extracts_title_year_and_first_author() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.datacite.org"
        assert request.url.path == "/dois/10.3929/ethz-b-000697688"
        creators = [{"nameType": "Personal", "familyName": "Ezzat", "name": "Ezzat, Mohamed"}]
        return httpx.Response(200, json=datacite_body(creators))

    record = fetch_datacite_record("10.3929/ethz-b-000697688", client_returning(handler))
    assert record == Record(title="A Thesis", year=2024, first_author="Ezzat")


def test_fetch_datacite_record_returns_none_on_404() -> None:
    assert fetch_datacite_record("10.1/missing", client_returning(lambda _r: httpx.Response(404))) is None


def test_fetch_datacite_record_returns_none_on_transport_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert fetch_datacite_record("10.1/abc", client_returning(handler)) is None


def test_fetch_datacite_record_tolerates_missing_year_and_creators() -> None:
    body: dict[str, object] = {
        "data": {"attributes": {"titles": [], "publicationYear": None, "creators": []}}
    }
    record = fetch_datacite_record("10.1/abc", client_returning(lambda _r: httpx.Response(200, json=body)))
    assert record == Record(title=None, year=None, first_author=None)


def test_first_family_name_falls_back_to_name_before_comma() -> None:
    assert first_family_name([{"nameType": "Personal", "name": "Samrock, Friedemann"}]) == "Samrock"


def test_first_family_name_uses_organisation_name() -> None:
    creators = [{"nameType": "Organizational", "name": "Swiss Federal Office of Topography"}]
    assert first_family_name(creators) == "Swiss Federal Office of Topography"


def test_first_family_name_rejects_datacite_placeholders() -> None:
    assert first_family_name([{"name": "(:unkn) unknown"}]) is None
    assert first_family_name([{"name": ":unav"}]) is None
    assert first_family_name([]) is None


def test_lookup_record_prefers_crossref() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org", "DataCite must not be asked when Crossref answers"
        body = {
            "message": {"title": ["Paper"], "issued": {"date-parts": [[2020]]}, "author": [{"family": "Doe"}]}
        }
        return httpx.Response(200, json=body)

    assert lookup_record("10.1/abc", client_returning(handler)) == Record("Paper", 2020, "Doe")


def test_lookup_record_falls_back_to_datacite_when_crossref_does_not_know_the_doi() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.crossref.org":
            return httpx.Response(404)
        return httpx.Response(200, json=datacite_body([{"nameType": "Personal", "familyName": "Ezzat"}]))

    assert lookup_record("10.3929/x", client_returning(handler)) == Record("A Thesis", 2024, "Ezzat")


def test_lookup_record_returns_none_when_neither_registry_knows_the_doi() -> None:
    assert lookup_record("10.1/none", client_returning(lambda _r: httpx.Response(404))) is None
