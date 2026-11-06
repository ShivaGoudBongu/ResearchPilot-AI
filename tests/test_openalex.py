"""Tests for OpenAlex response parsing and request error handling."""

import requests

from researchpilot.models import Paper
from researchpilot.openalex import OpenAlexClient, OpenAlexError, papers_from_payload, parse_work


FULL_WORK = {
    "id": "https://openalex.org/W1",
    "doi": "https://doi.org/10.1000/example",
    "title": "Graph neural networks for <i>drug</i> discovery",
    "publication_year": 2024,
    "authorships": [
        {"author": {"display_name": "Ada Lovelace"}},
        {"author": {"display_name": "Alan Turing"}},
        {"author": None, "raw_author_name": "Grace Hopper"},
    ],
    "abstract_inverted_index": {
        "discovery.": [4],
        "Models": [0],
        "molecules.": [2],
        "aid": [3],
        "represent": [1],
    },
    "primary_location": {
        "landing_page_url": "https://publisher.example/paper",
        "pdf_url": "https://publisher.example/paper.pdf",
    },
    "open_access": {"oa_url": "https://oa.example/paper"},
}


def test_parse_work_maps_a_complete_record():
    paper = parse_work(FULL_WORK)

    assert paper == Paper(
        title="Graph neural networks for drug discovery",
        authors=["Ada Lovelace", "Alan Turing", "Grace Hopper"],
        publication_year=2024,
        doi="https://doi.org/10.1000/example",
        abstract="Models represent molecules. aid discovery.",
        source_url="https://publisher.example/paper",
        openalex_id="https://openalex.org/W1",
    )


def test_parse_work_fills_gaps_when_metadata_is_missing():
    paper = parse_work({"id": "https://openalex.org/W9"})

    assert paper.title == "Untitled"
    assert paper.authors == []
    assert paper.publication_year is None
    assert paper.doi is None
    assert paper.abstract is None
    assert paper.source_url == "https://openalex.org/W9"


def test_parse_work_falls_back_through_source_urls_and_bare_dois():
    landing = parse_work(
        {
            "doi": "10.1000/bare",
            "primary_location": {"pdf_url": "https://files.example/a.pdf"},
            "open_access": {"oa_url": "https://oa.example/a"},
        }
    )
    pdf_only = parse_work({"primary_location": {"pdf_url": "https://files.example/a.pdf"}})
    oa_only = parse_work({"open_access": {"oa_url": "https://oa.example/a"}})
    bare_doi = parse_work({"doi": "doi:10.5555/abc"})

    assert landing.doi == "https://doi.org/10.1000/bare"
    assert landing.source_url == "https://files.example/a.pdf"
    assert pdf_only.source_url == "https://files.example/a.pdf"
    assert oa_only.source_url == "https://oa.example/a"
    assert bare_doi.doi == "https://doi.org/10.5555/abc"
    assert bare_doi.source_url == "https://doi.org/10.5555/abc"


def test_parse_work_reads_year_stored_as_text():
    assert parse_work({"publication_year": "2019"}).publication_year == 2019
    assert parse_work({"publication_year": "soon"}).publication_year is None


def _client(monkeypatch) -> OpenAlexClient:
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    return OpenAlexClient(timeout=5, session=requests.Session())


def test_search_parses_results_and_sends_expected_query(monkeypatch):
    client = _client(monkeypatch)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [FULL_WORK]}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(client._session, "get", fake_get)

    papers = client.search_papers("  graph neural networks  ", limit=50)

    assert captured["url"] == OpenAlexClient.BASE_URL
    assert captured["params"]["search"] == "graph neural networks"
    assert captured["params"]["per-page"] == 10
    assert "abstract_inverted_index" in captured["params"]["select"]
    assert "mailto" not in captured["params"]
    assert captured["timeout"] == 5
    assert "ResearchPilotAI" in captured["headers"]["User-Agent"]
    assert len(papers) == 1
    assert papers[0].title.startswith("Graph neural networks")


def test_search_includes_mailto_only_when_provided(monkeypatch):
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    client = OpenAlexClient(mailto="researcher@example.edu", session=requests.Session())
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(client._session, "get", fake_get)
    papers = client.search_papers("climate models")

    assert papers == []
    assert captured["params"]["mailto"] == "researcher@example.edu"


def test_search_rejects_a_blank_topic(monkeypatch):
    client = _client(monkeypatch)
    try:
        client.search_papers("   ")
    except ValueError as exc:
        assert "topic" in str(exc).lower()
    else:
        raise AssertionError("blank topic should raise ValueError")


def test_search_reports_timeout_connection_and_http_errors(monkeypatch):
    client = _client(monkeypatch)

    def timeout_get(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(client._session, "get", timeout_get)
    try:
        client.search_papers("quantum sensors")
    except OpenAlexError as exc:
        assert "too long" in str(exc)
    else:
        raise AssertionError("timeout should raise OpenAlexError")

    def connection_get(*args, **kwargs):
        raise requests.ConnectionError()

    monkeypatch.setattr(client._session, "get", connection_get)
    try:
        client.search_papers("quantum sensors")
    except OpenAlexError as exc:
        assert "Could not reach" in str(exc)
    else:
        raise AssertionError("connection failure should raise OpenAlexError")

    def http_get(*args, **kwargs):
        response = requests.Response()
        response.status_code = 503
        response.url = OpenAlexClient.BASE_URL
        response.reason = "Service Unavailable"
        response.raise_for_status()

    monkeypatch.setattr(client._session, "get", http_get)
    try:
        client.search_papers("quantum sensors")
    except OpenAlexError as exc:
        assert "HTTP 503" in str(exc)
    else:
        raise AssertionError("HTTP error should raise OpenAlexError")


def test_search_reports_invalid_json_and_unexpected_shape(monkeypatch):
    client = _client(monkeypatch)

    class BadJson:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: BadJson())
    try:
        client.search_papers("batteries")
    except OpenAlexError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("invalid JSON should raise OpenAlexError")

    class BadShape:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": {"not": "a list"}}

    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: BadShape())
    try:
        client.search_papers("batteries")
    except OpenAlexError as exc:
        assert "unexpected" in str(exc).lower()
    else:
        raise AssertionError("unexpected payload should raise OpenAlexError")


def test_search_treats_a_missing_results_list_as_empty(monkeypatch):
    client = _client(monkeypatch)

    class NoResults:
        def raise_for_status(self):
            return None

        def json(self):
            return {"meta": {"count": 0}}

    monkeypatch.setattr(client._session, "get", lambda *args, **kwargs: NoResults())
    assert client.search_papers("very obscure phrase") == []


def test_same_title_and_authors_with_different_identifiers_are_kept():
    authors = [{"author": {"display_name": "Ada Lovelace"}}]
    papers = papers_from_payload(
        {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "doi": "https://doi.org/10.1000/a",
                    "title": "AI Agents vs. Agentic AI",
                    "publication_year": 2024,
                    "authorships": authors,
                },
                {
                    "id": "https://openalex.org/W2",
                    "doi": "https://doi.org/10.1000/b",
                    "title": "AI Agents vs. Agentic AI",
                    "publication_year": 2025,
                    "authorships": authors,
                },
            ]
        }
    )

    assert [paper.openalex_id for paper in papers] == [
        "https://openalex.org/W1",
        "https://openalex.org/W2",
    ]
    assert [paper.publication_year for paper in papers] == [2024, 2025]


def test_duplicate_openalex_id_or_doi_is_kept_once():
    papers = papers_from_payload(
        {
            "results": [
                {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/same", "title": "First listing"},
                {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/same", "title": "Repeated work"},
                {"id": "https://openalex.org/W9", "doi": "https://doi.org/10.1000/same", "title": "Same DOI, other record"},
                {"id": "https://openalex.org/W3", "doi": "https://doi.org/10.1000/other", "title": "Distinct paper"},
            ]
        }
    )

    assert [paper.title for paper in papers] == ["First listing", "Distinct paper"]
