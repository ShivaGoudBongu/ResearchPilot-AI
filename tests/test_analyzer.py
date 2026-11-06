"""Tests for Gemini analysis. The API client is mocked."""

import pytest
from google.genai.errors import ClientError, ServerError

from researchpilot.analyzer import AnalysisError, analyze_paper
from researchpilot.models import Paper


FAKE_ANALYSIS = """## Research Objective
Study molecular graphs.

## Methodology
Not specified in the abstract.

## Key Findings
The model predicts binding.

## Limitations

### Author-reported limitations
Not specified in the abstract.

### Potential limitations to investigate
These are AI-generated hypotheses, not findings reported by the authors.
The abstract does not provide enough information for a meaningful hypothesis.
"""


def _install_fake_client(monkeypatch, generate):
    captured = {}

    class FakeModels:
        def generate_content(self, model, contents):
            captured["model"] = model
            captured["contents"] = contents
            return generate()

    class FakeClient:
        def __init__(self, api_key):
            captured["uses_test_key"] = api_key == "test-key"
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", FakeClient)
    return captured


def test_analyze_paper_sends_title_and_abstract_only(monkeypatch):
    captured = _install_fake_client(
        monkeypatch,
        lambda: type("Response", (), {"text": FAKE_ANALYSIS})(),
    )

    result = analyze_paper(
        title="Graph models",
        abstract="We predict binding from molecular graphs.",
    )

    assert "Research Objective" in result
    assert "Author-reported limitations" in result
    assert "Potential limitations to investigate" in result
    assert "AI-generated hypotheses" in result
    assert captured["uses_test_key"] is True
    assert captured["model"] == "gemini-3.5-flash-lite"
    prompt = captured["contents"]
    assert "Graph models" in prompt
    assert "We predict binding from molecular graphs." in prompt
    assert "### Author-reported limitations" in prompt
    assert "### Potential limitations to investigate" in prompt
    assert "These are AI-generated hypotheses, not findings reported by the authors." in prompt
    assert "Do not invent datasets, sample sizes, results, experiments, or weaknesses." in prompt
    assert "The abstract does not provide enough information for a meaningful hypothesis." in prompt
    assert "Not specified in the abstract" in prompt
    assert "test-key" not in prompt


def test_analyze_paper_rejects_a_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_client(*args, **kwargs):
        raise AssertionError("Gemini client should not be created")

    monkeypatch.setattr("researchpilot.analyzer.genai.Client", fail_client)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is missing"):
        analyze_paper("Title", "An abstract is present.")


def test_analyze_paper_rejects_a_blank_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    with pytest.raises(ValueError, match="GEMINI_API_KEY is missing"):
        analyze_paper("Title", "An abstract is present.")


def test_analyze_paper_rejects_a_missing_abstract(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="no abstract"):
        analyze_paper("Title", "   ")
    with pytest.raises(ValueError, match="no abstract"):
        analyze_paper("Title", None)


def test_analyze_paper_rejects_an_empty_model_response(monkeypatch):
    _install_fake_client(monkeypatch, lambda: type("Response", (), {"text": "  "})())

    with pytest.raises(ValueError, match="empty response"):
        analyze_paper("Title", "An abstract is present.")


def test_analyze_paper_explains_rate_limits_without_api_details(monkeypatch):
    def generate():
        raise ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}})

    _install_fake_client(monkeypatch, generate)

    with pytest.raises(AnalysisError, match="rate limiting") as caught:
        analyze_paper("Title", "An abstract is present.")

    assert "quota" not in str(caught.value)
    assert "test-key" not in str(caught.value)


def test_analyze_paper_explains_server_errors(monkeypatch):
    def generate():
        raise ServerError(503, {"error": {"status": "UNAVAILABLE", "message": "down"}})

    _install_fake_client(monkeypatch, generate)

    with pytest.raises(AnalysisError, match="temporarily unavailable"):
        analyze_paper("Title", "An abstract is present.")


def test_analyze_paper_explains_a_rejected_api_key(monkeypatch):
    def generate():
        raise ClientError(401, {"error": {"status": "UNAUTHENTICATED", "message": "bad key"}})

    _install_fake_client(monkeypatch, generate)

    with pytest.raises(AnalysisError, match="rejected the API key") as caught:
        analyze_paper("Title", "An abstract is present.")

    assert "test-key" not in str(caught.value)


def test_analysis_key_prefers_openalex_id_over_position():
    first = Paper(
        title="Same title",
        authors=["A"],
        publication_year=2020,
        doi="https://doi.org/10.1000/a",
        abstract="Alpha abstract",
        source_url=None,
        openalex_id="https://openalex.org/W1",
    )
    second = Paper(
        title="Same title",
        authors=["B"],
        publication_year=2020,
        doi="https://doi.org/10.1000/b",
        abstract="Beta abstract",
        source_url=None,
        openalex_id="https://openalex.org/W2",
    )

    assert first.analysis_key() == "openalex:https://openalex.org/W1"
    assert first.analysis_key() != second.analysis_key()


def test_analysis_key_falls_back_to_doi_then_title():
    with_doi = Paper(
        title="DOI paper",
        authors=[],
        publication_year=2018,
        doi="https://doi.org/10.1000/only",
        abstract="Abstract",
        source_url=None,
    )
    title_only = Paper(
        title="Title paper",
        authors=[],
        publication_year=None,
        doi=None,
        abstract="Abstract",
        source_url=None,
    )

    assert with_doi.analysis_key() == "doi:https://doi.org/10.1000/only"
    assert title_only.analysis_key() == "title:Title paper|year:unknown"


SAMPLE_ANALYSIS = """## Research Objective
Map molecular graphs.

## Methodology
The abstract describes a graph model.

## Key Findings
The model predicts binding.

## Limitations
Intro text that should not replace the subsections.

### Author-reported limitations
Not specified in the abstract.

### Potential limitations to investigate
These are AI-generated hypotheses, not findings reported by the authors.
Whether the graph model holds for larger molecules is not discussed.
"""


def test_parse_analysis_splits_sections_and_limitation_subsections():
    from researchpilot.analyzer import parse_analysis

    parsed = parse_analysis(SAMPLE_ANALYSIS)

    assert parsed is not None
    assert parsed["sections"]["Research Objective"] == "Map molecular graphs."
    assert parsed["sections"]["Key Findings"] == "The model predicts binding."
    assert parsed["author_reported"] == "Not specified in the abstract."
    assert "larger molecules" in parsed["potential"]
    assert "Map molecular graphs." not in parsed["potential"]


def test_parse_analysis_returns_none_when_a_main_section_is_missing():
    from researchpilot.analyzer import parse_analysis

    assert parse_analysis("## Research Objective\nOnly one section.") is None
    assert parse_analysis("") is None


def test_analysis_needs_request_skips_successful_results_and_retries_failures():
    from researchpilot.analyzer import analysis_needs_request

    assert analysis_needs_request(None) is True
    assert analysis_needs_request({"status": "error", "message": "try again"}) is True
    assert analysis_needs_request({"status": "ok", "text": "done"}) is False


def test_retain_analyses_keeps_each_result_with_its_paper_when_order_changes():
    from researchpilot.analyzer import retain_analyses

    first = Paper(
        title="First",
        authors=[],
        publication_year=2020,
        doi=None,
        abstract="First abstract",
        source_url=None,
        openalex_id="https://openalex.org/W1",
    )
    second = Paper(
        title="Second",
        authors=[],
        publication_year=2021,
        doi=None,
        abstract="Second abstract",
        source_url=None,
        openalex_id="https://openalex.org/W2",
    )
    analyses = {
        first.analysis_key(): {"status": "ok", "text": "analysis of first"},
        second.analysis_key(): {"status": "ok", "text": "analysis of second"},
    }

    retained = retain_analyses(analyses, [second, first])

    assert retained[first.analysis_key()]["text"] == "analysis of first"
    assert retained[second.analysis_key()]["text"] == "analysis of second"


def test_retain_analyses_drops_results_from_a_previous_search():
    from researchpilot.analyzer import retain_analyses

    previous = Paper(
        title="Previous",
        authors=[],
        publication_year=2019,
        doi=None,
        abstract="Old abstract",
        source_url=None,
        openalex_id="https://openalex.org/W3",
    )
    current = Paper(
        title="Current",
        authors=[],
        publication_year=2024,
        doi=None,
        abstract="New abstract",
        source_url=None,
        openalex_id="https://openalex.org/W4",
    )

    retained = retain_analyses(
        {previous.analysis_key(): {"status": "ok", "text": "old analysis"}},
        [current],
    )

    assert retained == {}


def test_retain_analyses_drops_results_from_other_papers():
    from researchpilot.analyzer import retain_analyses

    kept = Paper(
        title="Kept",
        authors=[],
        publication_year=2021,
        doi=None,
        abstract="Kept abstract",
        source_url=None,
        openalex_id="https://openalex.org/W9",
    )
    dropped = Paper(
        title="Dropped",
        authors=[],
        publication_year=2021,
        doi=None,
        abstract="Dropped abstract",
        source_url=None,
        openalex_id="https://openalex.org/W8",
    )
    analyses = {
        kept.analysis_key(): {"status": "ok", "text": "keep me"},
        dropped.analysis_key(): {"status": "ok", "text": "remove me"},
    }

    retained = retain_analyses(analyses, [kept])

    assert retained == {kept.analysis_key(): {"status": "ok", "text": "keep me"}}
    assert dropped.analysis_key() not in retained
