"""Selection rules and mocked multi-paper comparison. No live Gemini calls."""

import json
from dataclasses import replace

import pytest
from google.genai.errors import ClientError, ServerError

from researchpilot.analyzer import AnalysisError
from researchpilot.comparison import (
    INSUFFICIENT_HYPOTHESIS,
    NOT_REPORTED_GAP,
    NOT_SPECIFIED_LIMITATION,
    PRESENTATION_DISCLAIMER,
    ComparisonError,
    SelectionError,
    compare_papers,
    comparison_cache_key,
    parse_comparison,
    comparison_matches_selection,
    present_comparison,
    retain_comparisons,
    selection_errors,
    selection_key,
    validate_selection,
)
from researchpilot.models import Paper


def _paper(
    openalex_id: str | None,
    title: str,
    abstract: str | None = "An abstract with enough text.",
    *,
    year: int | None = 2020,
    doi: str | None = None,
) -> Paper:
    return Paper(
        title=title,
        authors=["Ada Lovelace"],
        publication_year=year,
        doi=doi,
        abstract=abstract,
        source_url=None,
        openalex_id=openalex_id,
    )


def _set(*papers: Paper) -> list[Paper]:
    return list(papers)


def test_valid_selections_of_three_four_and_five_papers():
    papers = [_paper(f"https://openalex.org/W{index}", f"Paper {index}") for index in range(1, 6)]

    for size in (3, 4, 5):
        chosen = papers[:size]
        assert selection_errors(chosen) == []
        validate_selection(chosen)
        assert selection_key(chosen)


def test_fewer_than_three_and_more_than_five_are_rejected():
    papers = [_paper(f"https://openalex.org/W{index}", f"Paper {index}") for index in range(1, 7)]

    too_few = selection_errors(papers[:2])
    too_many = selection_errors(papers)

    assert too_few == ["Select at least 3 papers to compare."]
    assert too_many == ["Select at most 5 papers to compare."]
    with pytest.raises(SelectionError, match="at least 3"):
        validate_selection(papers[:1])
    with pytest.raises(SelectionError, match="at most 5"):
        selection_key(papers)


def test_missing_and_whitespace_abstracts_are_rejected():
    missing = _paper("https://openalex.org/W1", "No abstract", abstract=None)
    blank = _paper("https://openalex.org/W2", "Blank abstract", abstract="   ")
    kept = [
        _paper("https://openalex.org/W3", "Kept paper"),
        _paper("https://openalex.org/W4", "Another paper"),
    ]

    errors = selection_errors([missing, blank, *kept])

    assert '"No abstract" has no abstract, so it cannot be compared.' in errors
    assert '"Blank abstract" has no abstract, so it cannot be compared.' in errors
    with pytest.raises(SelectionError, match="no abstract"):
        validate_selection([missing, *kept, _paper("https://openalex.org/W5", "Third")])


def test_duplicate_identifiers_are_rejected():
    first = _paper("https://openalex.org/W1", "First copy")
    duplicate = _paper("https://openalex.org/W1", "Same OpenAlex id")
    others = [
        _paper("https://openalex.org/W2", "Second"),
        _paper("https://openalex.org/W3", "Third"),
    ]

    errors = selection_errors([first, duplicate, *others])

    assert any("same identifier" in error for error in errors)
    with pytest.raises(SelectionError, match="same identifier"):
        selection_key([first, duplicate, *others])


def test_title_year_fallback_collision_is_rejected_and_distinct_titles_differ():
    shared = dict(doi=None, year=2018, abstract="Comparable abstract.")
    first = _paper(None, "Same title", **shared)
    second = _paper(None, "Same title", **shared)
    other = _paper(None, "Different title", **shared)
    third = _paper("https://openalex.org/W9", "Identified paper")

    assert first.analysis_key() == "title:Same title|year:2018"
    assert first.analysis_key() == second.analysis_key()
    assert other.analysis_key() == "title:Different title|year:2018"
    assert first.analysis_key() != other.analysis_key()

    errors = selection_errors([first, second, other])
    assert any("same identifier" in error for error in errors)

    chosen = [first, other, third]
    assert selection_errors(chosen) == []
    assert json.loads(selection_key(chosen)) == sorted(paper.analysis_key() for paper in chosen)


def test_selection_key_ignores_order_and_changes_when_the_set_changes():
    first = _paper("https://openalex.org/W1", "First")
    second = _paper("https://openalex.org/W2", "Second")
    third = _paper("https://openalex.org/W3", "Third")
    fourth = _paper("https://openalex.org/W4", "Fourth")

    forward = selection_key([first, second, third])
    backward = selection_key([third, first, second])
    replaced = selection_key([first, second, fourth])

    assert forward == backward
    assert forward != replaced
    assert json.loads(forward) == [
        first.analysis_key(),
        second.analysis_key(),
        third.analysis_key(),
    ]


def test_stored_comparison_is_visible_only_for_the_same_selection():
    papers = [_paper(f"https://openalex.org/W{index}", f"Paper {index}") for index in range(1, 5)]
    chosen = papers[:3]
    stored = {"selection_key": selection_key(chosen), "text": "comparison text"}

    assert comparison_matches_selection(stored, list(reversed(chosen))) is True
    assert comparison_matches_selection(stored["selection_key"], chosen) is True
    assert comparison_matches_selection(stored, papers[1:]) is False
    assert comparison_matches_selection(stored, chosen[:2]) is False
    assert comparison_matches_selection(stored, chosen + [_paper("https://openalex.org/W9", "Extra", abstract=None)]) is False
    assert comparison_matches_selection(None, chosen) is False
    assert comparison_matches_selection({"selection_key": ""}, chosen) is False
    assert comparison_matches_selection({"text": "orphan comparison"}, chosen) is False


def _numbered(count: int) -> list[Paper]:
    return [
        _paper(
            f"https://openalex.org/W{index}",
            f"Paper {index}",
            abstract=f"Abstract {index} describes a method and a result.",
        )
        for index in range(1, count + 1)
    ]


def _claim(text: str, paper_ids: list[str]) -> dict:
    return {"claim": text, "paper_ids": paper_ids}


def _payload(papers: list[Paper], *, gaps: list | None = None) -> dict:
    first = papers[0].analysis_key()
    cited = [paper.analysis_key() for paper in papers[:2]]
    if gaps is None:
        gaps = [_claim("The abstract states a gap.", [first])]
    return {
        "research_objectives": [_claim("The papers state different objectives.", [first])],
        "methodologies": [_claim("The papers use different methods.", cited)],
        "key_findings": [_claim("The papers report different findings.", [first])],
        "author_reported_limitations": [_claim("A limitation is stated.", [first])],
        "author_reported_gaps": gaps,
        "ai_inferred_gaps": [_claim("A hypothesis grounded in the abstract.", cited)],
    }


def _install_fake_gemini(monkeypatch, response):
    calls = {"count": 0, "contents": "", "model": "", "uses_test_key": False}

    class FakeModels:
        def generate_content(self, model, contents):
            calls["count"] += 1
            calls["contents"] = contents
            calls["model"] = model
            if isinstance(response, BaseException):
                raise response
            if callable(response):
                produced = response()
            else:
                produced = response
            if isinstance(produced, str):
                text = produced
            else:
                text = json.dumps(produced)
            return type("Response", (), {"text": text})()

    class FakeClient:
        def __init__(self, api_key):
            calls["uses_test_key"] = api_key == "test-key"
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", FakeClient)
    return calls


@pytest.mark.parametrize("count", [3, 4, 5])
def test_compare_papers_sends_one_request_for_the_selected_papers(monkeypatch, count):
    papers = _numbered(count)
    calls = _install_fake_gemini(monkeypatch, _payload(papers))

    result = compare_papers(list(reversed(papers)))

    assert calls["count"] == 1
    assert calls["model"] == "gemini-3.5-flash-lite"
    assert calls["uses_test_key"] is True
    assert "test-key" not in calls["contents"]
    assert "Do not invent datasets, sample sizes, experiments, results, citations" in calls["contents"]
    assert "None of the supplied abstracts report" in calls["contents"]
    assert "Do not name, cite, or attribute an objective, method, or finding" in calls["contents"]
    assert "wider research literature" in calls["contents"]
    for paper in papers:
        assert paper.analysis_key() in calls["contents"]
        assert paper.title in calls["contents"]
        assert paper.abstract.strip() in calls["contents"]
    assert result["selection_key"] == selection_key(papers)
    assert comparison_matches_selection(result, papers) is True
    assert result["research_objectives"][0]["paper_ids"] == [papers[0].analysis_key()]


def test_invalid_selection_is_rejected_before_the_api_request(monkeypatch):
    def fail_client(*args, **kwargs):
        raise AssertionError("Gemini client should not be created")

    monkeypatch.setattr("researchpilot.analyzer.genai.Client", fail_client)

    with pytest.raises(SelectionError, match="at least 3"):
        compare_papers(_numbered(2))


def test_compare_papers_rejects_a_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_client(*args, **kwargs):
        raise AssertionError("Gemini client should not be created")

    monkeypatch.setattr("researchpilot.analyzer.genai.Client", fail_client)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is missing"):
        compare_papers(_numbered(3))


def test_compare_papers_distinguishes_quota_rate_limits_and_server_errors(monkeypatch):
    papers = _numbered(3)
    calls = _install_fake_gemini(
        monkeypatch,
        ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "vendor-secret-detail"}}),
    )

    with pytest.raises(AnalysisError, match="quota is exhausted") as caught:
        compare_papers(papers)

    assert calls["count"] == 1
    assert "vendor-secret-detail" not in str(caught.value)
    assert "test-key" not in str(caught.value)

    _install_fake_gemini(
        monkeypatch,
        ClientError(429, {"error": {"status": "TOO_MANY_REQUESTS", "message": "vendor-secret-detail"}}),
    )
    with pytest.raises(AnalysisError, match="rate limiting"):
        compare_papers(papers)

    _install_fake_gemini(
        monkeypatch,
        ServerError(503, {"error": {"status": "UNAVAILABLE", "message": "down"}}),
    )
    with pytest.raises(AnalysisError, match="server error") as caught:
        compare_papers(papers)

    assert "temporarily unavailable" in str(caught.value)
    assert "not an authentication or quota failure" in str(caught.value)
    assert "down" not in str(caught.value)


def test_compare_papers_rejects_an_empty_response(monkeypatch):
    _install_fake_gemini(monkeypatch, "   ")

    with pytest.raises(ValueError, match="empty response"):
        compare_papers(_numbered(3))


def test_compare_papers_rejects_malformed_json_and_missing_sections(monkeypatch):
    papers = _numbered(3)
    _install_fake_gemini(monkeypatch, "{not valid json")

    with pytest.raises(ComparisonError, match="not valid JSON"):
        compare_papers(papers)

    incomplete = _payload(papers)
    del incomplete["key_findings"]
    _install_fake_gemini(monkeypatch, incomplete)
    with pytest.raises(ComparisonError, match="missing required sections"):
        compare_papers(papers)


def test_compare_papers_rejects_unknown_paper_identifiers(monkeypatch):
    papers = _numbered(3)
    payload = _payload(papers)
    payload["key_findings"] = [
        _claim("A finding from outside the selection.", ["openalex:https://openalex.org/W999"])
    ]
    _install_fake_gemini(monkeypatch, payload)

    with pytest.raises(ComparisonError, match="not in the selected set"):
        compare_papers(papers)


def test_missing_author_reported_gaps_are_explicitly_not_reported(monkeypatch):
    papers = _numbered(3)
    calls = _install_fake_gemini(monkeypatch, _payload(papers, gaps=[]))

    result = compare_papers(papers)

    assert result["author_reported_gaps"] == [{"claim": NOT_REPORTED_GAP, "paper_ids": []}]
    assert "Not reported in the supplied abstracts." in calls["contents"]
    assert "must not cite papers" in calls["contents"]
    assert result["selection_key"] == selection_key(papers)


def test_absence_statements_are_empty_states_not_cited_claims():
    papers = _numbered(3)
    cited = [papers[0].analysis_key(), papers[1].analysis_key()]
    payload = _payload(papers)
    payload["author_reported_limitations"] = [
        _claim("The supplied abstracts do not explicitly report limitations.", cited),
        _claim("The abstract states the sample excludes small banks.", [papers[2].analysis_key()]),
    ]
    payload["author_reported_gaps"] = [
        _claim("None of the supplied abstracts report a research gap.", cited),
    ]

    parsed = parse_comparison(json.dumps(payload), papers)

    assert parsed["author_reported_limitations"] == [
        {
            "claim": "The abstract states the sample excludes small banks.",
            "paper_ids": [papers[2].analysis_key()],
        }
    ]
    assert parsed["author_reported_gaps"] == [{"claim": NOT_REPORTED_GAP, "paper_ids": []}]

    only_absence = _payload(papers)
    only_absence["author_reported_limitations"] = [
        _claim("The supplied abstracts do not explicitly report limitations.", cited)
    ]
    parsed_only = parse_comparison(json.dumps(only_absence), papers)
    assert parsed_only["author_reported_limitations"] == [
        {"claim": NOT_SPECIFIED_LIMITATION, "paper_ids": []}
    ]

    stored = _comparison_result(
        papers,
        author_reported_limitations=[
            _claim("The supplied abstracts do not explicitly report limitations.", cited)
        ],
    )
    limitation = _section(present_comparison(stored, papers), "Author-Reported Limitations")["claims"][0]
    assert limitation["text"] == NOT_SPECIFIED_LIMITATION
    assert limitation["paper_ids"] == []
    assert limitation["paper_titles"] == []
    assert limitation["empty"] is True


def _comparison_result(papers: list[Paper], **sections: list) -> dict:
    result = {
        "selection_key": selection_key(papers),
        "scope": "model scope that must not replace the fixed disclaimer",
        "research_objectives": [_claim("Objective text.", [papers[0].analysis_key()])],
        "methodologies": [_claim("Method text.", [papers[0].analysis_key()])],
        "key_findings": [_claim("Finding text.", [papers[0].analysis_key()])],
        "author_reported_limitations": [_claim("Limitation text.", [papers[0].analysis_key()])],
        "author_reported_gaps": [_claim("Reported gap.", [papers[0].analysis_key()])],
        "ai_inferred_gaps": [_claim("Inferred hypothesis.", [papers[0].analysis_key()])],
    }
    result.update(sections)
    return result


def _section(view: dict, label: str) -> dict:
    return next(section for section in view["sections"] if section["label"] == label)


def test_present_comparison_maps_claims_to_selected_titles():
    papers = [
        _paper("https://openalex.org/W1", "Alpha Study"),
        _paper("https://openalex.org/W2", "Beta Study"),
        _paper("https://openalex.org/W3", "Gamma Study"),
    ]
    both = [papers[0].analysis_key(), papers[2].analysis_key()]
    result = _comparison_result(
        papers,
        methodologies=[_claim("Alpha and Gamma use different methods.", both)],
    )

    view = present_comparison(result, list(reversed(papers)))
    claim = _section(view, "Methodologies")["claims"][0]

    assert claim["text"] == "Alpha and Gamma use different methods."
    assert claim["paper_ids"] == both
    assert claim["paper_titles"] == ["Alpha Study", "Gamma Study"]
    assert claim["ai_generated"] is True
    assert claim["based_on"] == "abstracts"
    assert view["disclaimer"] == PRESENTATION_DISCLAIMER
    assert "model scope" not in view["disclaimer"]


def test_present_comparison_labels_sections_and_empty_states():
    papers = _numbered(3)
    result = _comparison_result(
        papers,
        research_objectives=[],
        author_reported_gaps=[],
        ai_inferred_gaps=[],
    )

    view = present_comparison(result, papers)
    labels = [section["label"] for section in view["sections"]]

    assert labels == [
        "Research Objectives",
        "Methodologies",
        "Key Findings",
        "Author-Reported Limitations",
        "Author-Reported Research Gaps",
        "AI-Inferred Potential Research Gaps",
    ]
    assert _section(view, "Research Objectives")["claims"][0]["text"] == (
        "Not specified in the supplied abstracts."
    )
    assert _section(view, "Author-Reported Research Gaps")["kind"] == "author_reported"
    assert _section(view, "Author-Reported Research Gaps")["claims"][0]["text"] == NOT_REPORTED_GAP
    inferred = _section(view, "AI-Inferred Potential Research Gaps")
    assert inferred["kind"] == "ai_inferred"
    assert inferred["claims"][0]["text"] == INSUFFICIENT_HYPOTHESIS
    assert inferred["claims"][0]["paper_titles"] == []
    assert view["disclaimer"] == (
        "AI-generated comparison based only on the selected titles and abstracts. "
        "Verify claims against the full papers. "
        "This comparison cannot establish gaps across the entire research literature."
    )


def test_present_comparison_rejects_unknown_identifiers_and_other_selections():
    papers = _numbered(4)
    chosen = papers[:3]
    result = _comparison_result(chosen)
    result["key_findings"] = [
        _claim("Outside the selection.", ["openalex:https://openalex.org/W999"])
    ]

    with pytest.raises(ComparisonError, match="not in the current selection"):
        present_comparison(result, chosen)

    matching = _comparison_result(chosen)
    assert present_comparison(matching, list(reversed(chosen)))["selection_key"] == selection_key(chosen)
    with pytest.raises(ComparisonError, match="does not match"):
        present_comparison(matching, papers[1:])


def test_missing_abstract_paper_cannot_be_sent_or_labeled(monkeypatch):
    missing = _paper(
        "https://openalex.org/W2965586107",
        "Data Mining Techniques for Fraud Detection in Banking Sector",
        abstract=None,
    )
    selected = _numbered(3)
    calls = _install_fake_gemini(monkeypatch, _payload(selected))

    with pytest.raises(SelectionError, match="no abstract"):
        compare_papers([missing, *selected])
    assert calls["count"] == 0
    assert missing.title not in calls["contents"]

    forged = _payload(selected)
    forged["research_objectives"] = [
        _claim(
            "Data Mining Techniques for Fraud Detection in Banking Sector aims to mine transactions.",
            [missing.analysis_key()],
        )
    ]
    with pytest.raises(ComparisonError, match="not in the selected set"):
        parse_comparison(json.dumps(forged), selected)

    view = present_comparison(_comparison_result(selected), selected)
    titles = [
        title
        for section in view["sections"]
        for claim in section["claims"]
        for title in claim["paper_titles"]
    ]
    assert missing.title not in titles
    assert selected[0].title in titles


def test_cache_key_tracks_abstract_content_not_only_the_identifier():
    papers = _numbered(3)
    original = comparison_cache_key(papers)
    reordered = comparison_cache_key(list(reversed(papers)))
    changed = comparison_cache_key(
        [replace(papers[0], abstract="A rewritten abstract with different evidence."), *papers[1:]]
    )
    identifier_only = selection_key(papers)

    assert original == reordered
    assert changed != original
    stored = {
        original: {"status": "ok", "content_key": original},
        identifier_only: {"status": "ok", "selection_key": identifier_only},
    }
    kept = retain_comparisons(stored, papers)
    assert list(kept) == [original]
    assert retain_comparisons(stored, [replace(papers[0], abstract="A rewritten abstract with different evidence."), *papers[1:]]) == {}
