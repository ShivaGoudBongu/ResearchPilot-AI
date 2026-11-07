"""Word export repeats saved results and does not call Gemini."""

import inspect
from dataclasses import replace
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from docx.shared import Inches

from researchpilot.analyzer import DISCLAIMER
from researchpilot.citations import STYLE_APA, STYLE_HARVARD
from researchpilot.comparison import (
    PRESENTATION_DISCLAIMER,
    ComparisonError,
    comparison_cache_key,
    selection_key,
)
from researchpilot.export import ExportError, comparison_docx, paper_analysis_docx
from researchpilot.models import Paper

ANALYSIS = """## Research Objective
Alpha objective only.

## Methodology
A method from the abstract.

## Key Findings
Alpha finding only.

## Limitations

### Author-reported limitations
The abstract states a small sample.

### Potential limitations to investigate
Whether the reported method was compared with a baseline is not stated.
"""

GENERATED = date(2026, 11, 6)


def _paper(**overrides) -> Paper:
    values = {
        "title": "Graph neural networks for naïve discovery",
        "authors": ["Ada Lovelace"],
        "publication_year": 2024,
        "doi": "https://doi.org/10.1000/example",
        "abstract": "This secret abstract sentence must stay out of the report.",
        "source_url": "https://publisher.example/paper",
        "openalex_id": "https://openalex.org/W1",
        "venue": "Nature Machine Intelligence",
    }
    values.update(overrides)
    return Paper(**values)


def _comparison_papers() -> list[Paper]:
    return [
        _paper(
            title="Alpha study",
            authors=["Ada Lovelace"],
            openalex_id="https://openalex.org/W1",
            doi="https://doi.org/10.1000/alpha",
            abstract="Alpha abstract is long enough to compare.",
        ),
        _paper(
            title="Gamma study",
            authors=["Grace Hopper"],
            publication_year=2021,
            openalex_id="https://openalex.org/W2",
            doi="https://doi.org/10.1000/gamma",
            abstract="Gamma abstract is long enough to compare.",
        ),
        _paper(
            title="Beta study",
            authors=["Alan Turing"],
            publication_year=2019,
            openalex_id="https://openalex.org/W3",
            doi="https://doi.org/10.1000/beta",
            abstract="Beta abstract is long enough to compare.",
        ),
    ]


def _result(papers: list[Paper]) -> dict:
    cited = [papers[0].analysis_key(), papers[1].analysis_key()]
    return {
        "selection_key": selection_key(papers),
        "scope": "from the model",
        "research_objectives": [
            {"claim": "Objective claim about the abstracts. doi:10.1000/keep-this", "paper_ids": [papers[0].analysis_key()]}
        ],
        "methodologies": [{"claim": "Methodology claim citing two papers.", "paper_ids": cited}],
        "key_findings": [{"claim": "Finding claim from the abstracts.", "paper_ids": [papers[0].analysis_key()]}],
        "author_reported_limitations": [
            {"claim": "Limitation claim from the abstracts.", "paper_ids": [papers[0].analysis_key()]}
        ],
        "author_reported_gaps": [{"claim": "Not reported in the supplied abstracts.", "paper_ids": []}],
        "ai_inferred_gaps": [
            {"claim": "Inferred gap hypothesis from the abstracts.", "paper_ids": [papers[2].analysis_key()]}
        ],
    }


def _cached(papers: list[Paper], result: dict | None = None) -> dict:
    content_key = comparison_cache_key(papers)
    payload = _result(papers) if result is None else result
    return {
        "status": "ok",
        "result": payload,
        "selection_key": payload["selection_key"],
        "content_key": content_key,
    }


def _text(payload: bytes) -> str:
    document = Document(BytesIO(payload))
    parts = [paragraph.text for paragraph in document.paragraphs]
    section = document.sections[0]
    parts.append(section.header.paragraphs[0].text)
    parts.append(section.footer.paragraphs[0].text)
    return "\n".join(parts)


def test_paper_analysis_docx_contains_only_the_saved_analysis():
    paper = _paper()
    payload = paper_analysis_docx(paper, ANALYSIS, STYLE_APA, generated_on=GENERATED)
    other = _paper(title="Unrelated paper", openalex_id="https://openalex.org/W9")

    assert payload.startswith(b"PK")
    reopened = Document(BytesIO(payload))
    section = reopened.sections[0]
    assert section.top_margin == Inches(1)
    assert section.left_margin == Inches(1)
    assert "ResearchPilot AI" in section.header.paragraphs[0].text
    assert "Not a systematic literature review" in section.footer.paragraphs[0].text
    assert "PAGE" in section.footer._element.xml

    text = _text(payload)
    assert "Paper analysis report" in text
    assert "6 November 2026" in text
    assert DISCLAIMER in text
    assert "It is not a systematic literature review." in text
    assert "Graph neural networks for naïve discovery" in text
    assert "Ada Lovelace" in text
    assert "2024" in text
    assert "Nature Machine Intelligence" in text
    assert "https://doi.org/10.1000/example" in text
    assert "https://publisher.example/paper" in text
    assert paper.analysis_key() in text
    assert other.analysis_key() not in text
    assert "Alpha objective only." in text
    assert "A method from the abstract." in text
    assert "Alpha finding only." in text
    assert "The abstract states a small sample." in text
    assert "Whether the reported method was compared with a baseline is not stated." in text
    assert "Lovelace, A. (2024). Graph neural networks for naïve discovery." in text
    assert "This secret abstract sentence must stay out of the report." not in text
    assert "INVENTED SAMPLE SIZE 99991" not in text
    assert "completed systematic literature review" not in text


def test_missing_metadata_is_labelled_and_not_invented():
    paper = _paper(
        authors=[],
        publication_year=None,
        doi=None,
        source_url=None,
        venue=None,
        title="Only a title",
    )
    text = _text(paper_analysis_docx(paper, ANALYSIS, STYLE_HARVARD, generated_on=GENERATED))

    assert "Authors: Not available" in text
    assert "Year: Not available" in text
    assert "DOI: Not available" in text
    assert "Source URL: Not available" in text
    assert "Venue:" not in text
    assert "Only a title. (2024)." not in text
    assert "Only a title. (n.d.)." in text
    assert "Check before use: authors, year, venue, DOI missing." in text
    for invented in ("Vol.", "pp.", "Issue", "Unknown journal"):
        assert invented not in text


def test_unusable_analysis_is_refused():
    paper = _paper()
    with pytest.raises(ExportError):
        paper_analysis_docx(paper, "This reply has no sections.", STYLE_APA)
    with pytest.raises(ExportError):
        paper_analysis_docx(paper, "   ", STYLE_APA)


def test_comparison_docx_keeps_presenter_claims_and_references():
    papers = _comparison_papers()
    payload = comparison_docx(papers, _cached(papers), STYLE_HARVARD, generated_on=GENERATED)
    text = _text(payload)

    assert payload.startswith(b"PK")
    assert Document(BytesIO(payload)).paragraphs
    assert "Comparison report" in text
    assert "6 November 2026" in text
    assert PRESENTATION_DISCLAIMER in text
    assert "It is not a systematic literature review." in text
    assert "Alpha study" in text
    assert "Gamma study" in text
    assert "Beta study" in text
    for paper in papers:
        assert paper.analysis_key() in text
    assert "https://openalex.org/W9" not in text
    assert "Objective claim about the abstracts. doi:10.1000/keep-this" in text
    assert "Methodology claim citing two papers." in text
    assert "Finding claim from the abstracts." in text
    assert "Limitation claim from the abstracts." in text
    assert "Not reported in the supplied abstracts." in text
    assert "Inferred gap hypothesis from the abstracts." in text
    assert f"Papers: Alpha study ({papers[0].analysis_key()})" in text
    assert f"Papers: Beta study ({papers[2].analysis_key()})" in text
    assert text.index("Hopper, G.") < text.index("Lovelace, A.") < text.index("Turing, A.")
    assert "Available at: https://doi.org/10.1000/alpha" in text
    assert "INVENTED SAMPLE SIZE 99991" not in text


def test_stale_or_invalid_comparisons_are_not_exported():
    papers = _comparison_papers()
    cached = _cached(papers)
    revised = [replace(papers[0], abstract="A rewritten abstract with different evidence."), *papers[1:]]
    with pytest.raises(ExportError):
        comparison_docx(revised, cached, STYLE_APA)

    other = [
        *papers[1:],
        _paper(title="Delta study", openalex_id="https://openalex.org/W4", abstract="Delta abstract is long enough."),
    ]
    forged = dict(cached)
    forged["content_key"] = comparison_cache_key(other)
    with pytest.raises(ComparisonError):
        comparison_docx(other, forged, STYLE_APA)

    failed = dict(cached)
    failed["status"] = "error"
    with pytest.raises(ExportError):
        comparison_docx(papers, failed, STYLE_APA)


def test_export_does_not_call_gemini(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("Word export must not call Gemini.")

    monkeypatch.setattr("researchpilot.analyzer.generate_text", explode)
    monkeypatch.setattr("researchpilot.comparison.compare_papers", explode)
    papers = _comparison_papers()
    paper_analysis_docx(_paper(), ANALYSIS, STYLE_APA, generated_on=GENERATED)
    comparison_docx(papers, _cached(papers), STYLE_APA, generated_on=GENERATED)

    source = inspect.getsource(inspect.getmodule(paper_analysis_docx))
    assert "generate_text" not in source
    assert "analyze_paper" not in source
    assert "compare_papers" not in source
