"""Streamlit app checks. These tests do not call OpenAlex or Gemini."""

from dataclasses import replace
from pathlib import Path

from streamlit.testing.v1 import AppTest

from researchpilot.comparison import (
    PRESENTATION_DISCLAIMER,
    ComparisonError,
    comparison_cache_key,
    selection_key,
)
from researchpilot.models import Paper

APP = Path(__file__).resolve().parents[1] / "app.py"

ANALYSIS = """## Research Objective
Alpha objective only.

## Methodology
A method from the abstract.

## Key Findings
Alpha finding only.

## Limitations

### Author-reported limitations
Not specified in the abstract.

### Potential limitations to investigate
Whether the reported method was compared with a baseline is not stated.
"""


def _paper(openalex_id: str, title: str, abstract: str | None, source_url: str | None) -> Paper:
    return Paper(
        title=title,
        authors=["Ada Lovelace", "Alan Turing", "Grace Hopper", "Katherine Johnson"],
        publication_year=2020,
        doi="https://doi.org/10.1000/example",
        abstract=abstract,
        source_url=source_url,
        openalex_id=openalex_id,
    )


def test_app_starts_and_shows_the_search_page():
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert not app.exception
    assert app.title[0].value == "ResearchPilot AI"
    assert app.button[0].label == "Search"


def test_saved_analysis_stays_on_its_paper_inside_the_expander():
    analysed = _paper(
        "https://openalex.org/W1",
        "Analysed paper",
        "This abstract is long enough to analyse.",
        "https://publisher.example/analysed",
    )
    missing_abstract = _paper(
        "https://openalex.org/W2",
        "Paper without an abstract",
        None,
        "https://publisher.example/other",
    )
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["papers"] = [analysed, missing_abstract]
    app.session_state["analyses"] = {
        analysed.analysis_key(): {"status": "ok", "text": ANALYSIS},
    }
    app.session_state["error"] = None
    app.session_state["searched_topic"] = "graphs"
    app.run()

    assert not app.exception
    visible = "\n".join(item.value for item in app.markdown)
    assert "Analysed paper" in visible
    assert "Paper without an abstract" in visible
    assert any(
        "Alpha objective only." in "\n".join(getattr(child, "value", "") or "" for child in expander)
        for expander in app.expander
    )
    assert len(app.link_button) == 2
    assert all(item.value == "View source" for item in app.link_button)

    captions = "\n".join(item.value for item in app.caption)
    assert "Alpha objective only." in visible
    assert "Alpha finding only." in visible
    assert "Author-reported limitations" in visible
    assert "AI-generated hypotheses" in captions
    assert "title and abstract only" in captions
    assert app.session_state["analyses"][analysed.analysis_key()]["text"] == ANALYSIS
    assert missing_abstract.analysis_key() not in app.session_state["analyses"]

    analyse_buttons = [button for button in app.button if "Analyse" in button.label or "Retry" in button.label]
    assert len(analyse_buttons) == 1
    assert analyse_buttons[0].label == "Analyse with AI"
    assert analyse_buttons[0].proto.disabled is True
    assert [box.label for box in app.checkbox] == ["Select for comparison"]
    assert "cannot be selected for comparison" in "\n".join(item.value for item in app.caption)


def _flow(app: AppTest) -> list[tuple[str, str]]:
    flow = []
    for node in app:
        kind = getattr(node, "type", "")
        if kind == "markdown":
            flow.append((kind, node.value))
        elif kind == "caption":
            flow.append((kind, node.value))
        elif kind == "checkbox":
            flow.append((kind, node.label))
    return flow


def _title_index(flow: list[tuple[str, str]], title: str) -> int:
    return next(index for index, (kind, text) in enumerate(flow) if kind == "markdown" and title in text)


def test_missing_abstract_notice_appears_under_its_own_title():
    mining = _paper(
        "https://openalex.org/W2",
        "Data Mining Techniques for Fraud Detection in Banking Sector",
        "This abstract is long enough to compare.",
        "https://example/mining",
    )
    imbalanced = _paper(
        "https://openalex.org/W3",
        "Effective detection of sophisticated online banking fraud on extremely imbalanced data",
        None,
        "https://example/imbalanced",
    )
    machine_learning = _paper(
        "https://openalex.org/W6",
        "Fraud Detection in Banking using ML",
        "This abstract is also long enough to compare.",
        "https://example/ml",
    )
    temporal = _paper(
        "https://openalex.org/W7",
        "Temporal Network Analytics for Fraud Detection in the Banking Sector",
        None,
        "https://example/temporal",
    )
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["papers"] = [mining, imbalanced, machine_learning, temporal]
    app.session_state["error"] = None
    app.session_state["searched_topic"] = "fraud detection banking"
    app.session_state["analyses"] = {}
    app.run()

    assert not app.exception
    flow = _flow(app)
    mining_at = _title_index(flow, mining.title)
    imbalanced_at = _title_index(flow, imbalanced.title)
    learning_at = _title_index(flow, machine_learning.title)
    temporal_at = _title_index(flow, temporal.title)
    imbalanced_notice = next(
        index for index, (kind, text) in enumerate(flow) if kind == "caption" and imbalanced.title in text
    )
    temporal_notice = next(
        index for index, (kind, text) in enumerate(flow) if kind == "caption" and temporal.title in text
    )

    assert mining_at < imbalanced_at < imbalanced_notice < learning_at
    assert learning_at < temporal_at < temporal_notice
    assert not any(kind == "checkbox" for kind, _text in flow[imbalanced_at:learning_at])
    assert not any(kind == "checkbox" for kind, _text in flow[temporal_at:])
    assert [text for kind, text in flow if kind == "checkbox"] == ["Select for comparison", "Select for comparison"]


def _comparison_payload(papers: list[Paper], claim: str = "Objective claim about the abstracts.") -> dict:
    cited = [papers[0].analysis_key(), papers[1].analysis_key()]
    finding = {"claim": claim, "paper_ids": [papers[0].analysis_key()]}
    return {
        "selection_key": selection_key(papers),
        "scope": "from the model",
        "research_objectives": [finding],
        "methodologies": [{"claim": "Methodology claim citing two papers.", "paper_ids": cited}],
        "key_findings": [{"claim": "Finding claim from the abstracts.", "paper_ids": [papers[0].analysis_key()]}],
        "author_reported_limitations": [
            {"claim": "Limitation claim from the abstracts.", "paper_ids": [papers[0].analysis_key()]}
        ],
        "author_reported_gaps": [
            {"claim": "Not reported in the supplied abstracts.", "paper_ids": []}
        ],
        "ai_inferred_gaps": [
            {"claim": "Inferred gap hypothesis from the abstracts.", "paper_ids": [papers[2].analysis_key()]}
        ],
    }


def _markdown(app: AppTest) -> str:
    return "\n".join(item.value for item in app.markdown)


def _captions(app: AppTest) -> str:
    return "\n".join(item.value for item in app.caption)


def _compare_button(app: AppTest):
    return next(button for button in app.button if button.label == "Compare Selected Papers")


def _search_button(app: AppTest):
    return next(button for button in app.button if button.label == "Search")


def _stored_comparison(papers: list[Paper], result: dict) -> dict:
    content_key = comparison_cache_key(papers)
    return {
        content_key: {
            "status": "ok",
            "result": result,
            "selection_key": result["selection_key"],
            "content_key": content_key,
        }
    }


def _load(papers: list[Paper], **state) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["papers"] = papers
    app.session_state["error"] = None
    app.session_state["searched_topic"] = "graphs"
    app.session_state["analyses"] = state.get("analyses", {})
    app.session_state["comparisons"] = state.get("comparisons", {})
    app.run()
    assert not app.exception
    return app


def test_comparison_waits_for_the_button_and_follows_the_selection(monkeypatch):
    calls = {"compare": 0}
    papers = [
        _paper(f"https://openalex.org/W{index}", f"Paper {index}", f"Abstract {index} is long enough.", f"https://example/{index}")
        for index in range(1, 5)
    ]
    papers.append(_paper("https://openalex.org/W5", "Paper without an abstract", None, "https://example/5"))
    stale_papers = papers[1:4]
    stale = _comparison_payload(stale_papers, "STALE SELECTION CLAIM")

    def fake_compare(selected):
        calls["compare"] += 1
        return _comparison_payload(selected)

    monkeypatch.setattr("researchpilot.comparison.compare_papers", fake_compare)
    app = _load(papers, comparisons=_stored_comparison(stale_papers, stale))

    boxes = list(app.checkbox)
    assert len(boxes) == 4
    assert "cannot be selected for comparison" in _captions(app)
    assert _compare_button(app).proto.disabled is True
    assert calls["compare"] == 0
    assert "STALE SELECTION CLAIM" not in _markdown(app)

    for box in boxes[:2]:
        box.check()
    app.run()
    assert calls["compare"] == 0
    assert "2 papers selected" in _captions(app)
    assert _compare_button(app).proto.disabled is True
    assert "Objective claim about the abstracts." not in _markdown(app)

    boxes = list(app.checkbox)
    boxes[2].check().run()
    assert calls["compare"] == 0
    assert "3 papers selected" in _captions(app)
    assert _compare_button(app).proto.disabled is False
    assert "Objective claim about the abstracts." not in _markdown(app)
    assert "STALE SELECTION CLAIM" not in _markdown(app)

    _compare_button(app).click().run()
    assert not app.exception
    assert calls["compare"] == 1
    visible = _markdown(app)
    captions = _captions(app)
    assert "Research Objectives" in visible
    assert "Methodologies" in visible
    assert "Key Findings" in visible
    assert "Author-Reported Limitations" in visible
    assert "Author-Reported Research Gaps" in visible
    assert "AI-Inferred Potential Research Gaps" in visible
    assert "Objective claim about the abstracts." in visible
    assert "Methodology claim citing two papers." in visible
    assert "Inferred gap hypothesis from the abstracts." in visible
    assert "Papers: Paper 1; Paper 2" in captions
    assert "Papers: Paper 3" in captions
    assert "AI-generated from the selected abstracts." in captions
    assert PRESENTATION_DISCLAIMER in captions
    assert "from the model" not in captions
    assert "Taken from wording in the selected abstracts. Not independently verified." in captions
    assert "AI-inferred hypotheses from the selected abstracts" in captions
    assert "not independently verified" in captions

    boxes = list(app.checkbox)
    boxes[0].uncheck()
    boxes[3].check()
    app.run()
    assert calls["compare"] == 1
    assert "Objective claim about the abstracts." not in _markdown(app)
    assert "STALE SELECTION CLAIM" in _markdown(app)

    boxes = list(app.checkbox)
    boxes[0].check()
    boxes[3].uncheck()
    app.run()
    assert calls["compare"] == 1
    assert "Objective claim about the abstracts." in _markdown(app)

    _compare_button(app).click().run()
    assert calls["compare"] == 1


def test_new_search_clears_selection_and_drops_unrelated_comparisons(monkeypatch):
    calls = {"compare": 0}
    first = [
        _paper(f"https://openalex.org/W{index}", f"Paper {index}", f"Abstract {index} is long enough.", f"https://example/{index}")
        for index in range(1, 4)
    ]
    held = {"papers": first}

    def fake_compare(selected):
        calls["compare"] += 1
        return _comparison_payload(selected)

    class FakeClient:
        def search_papers(self, topic):
            return held["papers"]

    monkeypatch.setattr("researchpilot.comparison.compare_papers", fake_compare)
    monkeypatch.setattr("researchpilot.openalex.OpenAlexClient", FakeClient)

    kept = first[0]
    app = _load(
        first,
        analyses={kept.analysis_key(): {"status": "ok", "text": ANALYSIS}},
        comparisons=_stored_comparison(first, _comparison_payload(first)),
    )
    for box in app.checkbox:
        box.check()
    app.run()
    assert calls["compare"] == 0
    assert "Objective claim about the abstracts." in _markdown(app)

    app.text_input[0].set_value("graphs again")
    _search_button(app).click().run()
    assert not app.exception
    assert calls["compare"] == 0
    assert "0 papers selected" in _captions(app)
    assert "Objective claim about the abstracts." not in _markdown(app)
    assert all(not box.value for box in app.checkbox)
    assert comparison_cache_key(first) in app.session_state["comparisons"]
    assert app.session_state["analyses"][kept.analysis_key()]["text"] == ANALYSIS

    for box in app.checkbox:
        box.check()
    app.run()
    assert calls["compare"] == 0
    assert "Objective claim about the abstracts." in _markdown(app)

    replacement = [
        kept,
        _paper("https://openalex.org/W9", "Fresh paper", "A new abstract for the next search.", "https://example/9"),
        _paper("https://openalex.org/W10", "Another fresh paper", None, "https://example/10"),
    ]
    held["papers"] = replacement
    app.text_input[0].set_value("different topic")
    _search_button(app).click().run()
    assert not app.exception
    assert calls["compare"] == 0
    assert "Objective claim about the abstracts." not in _markdown(app)
    assert "0 papers selected" in _captions(app)
    assert len(app.checkbox) == 2
    assert "cannot be selected for comparison" in _captions(app)
    assert comparison_cache_key(first) not in app.session_state["comparisons"]
    assert app.session_state["analyses"][kept.analysis_key()]["text"] == ANALYSIS
    assert _compare_button(app).proto.disabled is True


def test_failed_comparison_can_be_retried_without_another_search(monkeypatch):
    calls = {"compare": 0}
    papers = [
        _paper(f"https://openalex.org/W{index}", f"Paper {index}", f"Abstract {index} is long enough.", f"https://example/{index}")
        for index in range(1, 4)
    ]

    def fake_compare(selected):
        calls["compare"] += 1
        if calls["compare"] == 1:
            raise ComparisonError("Gemini returned a comparison that was not valid JSON.")
        return _comparison_payload(selected)

    monkeypatch.setattr("researchpilot.comparison.compare_papers", fake_compare)
    app = _load(papers)
    for box in app.checkbox:
        box.check()
    app.run()
    _compare_button(app).click().run()

    assert calls["compare"] == 1
    assert any("not valid JSON" in item.value for item in app.error)
    assert "Objective claim about the abstracts." not in _markdown(app)
    assert _compare_button(app).proto.disabled is False

    _compare_button(app).click().run()
    assert calls["compare"] == 2
    assert "Objective claim about the abstracts." in _markdown(app)
    assert not any("not valid JSON" in item.value for item in app.error)


def test_missing_abstract_is_not_compared_and_old_identifier_cache_is_ignored(monkeypatch):
    missing = Paper(
        title="Data Mining Techniques for Fraud Detection in Banking Sector",
        authors=["A. Author"],
        publication_year=2018,
        doi="https://doi.org/10.1109/ccaa.2018.8777535",
        abstract=None,
        source_url="https://example/missing",
        openalex_id="https://openalex.org/W2965586107",
    )
    selected = [
        _paper(
            f"https://openalex.org/W{index}",
            f"Paper {index}",
            f"Abstract {index} is long enough.",
            f"https://example/{index}",
        )
        for index in range(1, 4)
    ]
    calls = {"compare": 0, "titles": [], "abstracts": []}

    def fake_compare(papers):
        calls["compare"] += 1
        calls["titles"] = [paper.title for paper in papers]
        calls["abstracts"] = [paper.abstract for paper in papers]
        return _comparison_payload(papers)

    monkeypatch.setattr("researchpilot.comparison.compare_papers", fake_compare)
    stale = _comparison_payload(selected, "STALE IDENTIFIER CLAIM")
    app = _load(
        [missing, *selected],
        comparisons={
            selection_key(selected): {
                "status": "ok",
                "result": stale,
                "selection_key": selection_key(selected),
            }
        },
    )

    assert len(app.checkbox) == 3
    assert (
        '"Data Mining Techniques for Fraud Detection in Banking Sector" '
        'has no abstract, so it cannot be selected for comparison.'
    ) in _captions(app)
    for box in app.checkbox:
        box.check()
    app.run()
    assert "STALE IDENTIFIER CLAIM" not in _markdown(app)

    _compare_button(app).click().run()
    assert not app.exception
    assert calls["compare"] == 1
    assert calls["titles"] == [paper.title for paper in selected]
    assert missing.title not in calls["titles"]
    paper_lines = [item.value for item in app.caption if "Papers:" in item.value]
    assert paper_lines
    assert all(missing.title not in line for line in paper_lines)

    revised = [replace(selected[0], abstract="A rewritten abstract with different evidence."), *selected[1:]]
    app.session_state["papers"] = [missing, *revised]
    app.run()
    assert "Objective claim about the abstracts." not in _markdown(app)
    _compare_button(app).click().run()
    assert calls["compare"] == 2
    assert calls["titles"] == [paper.title for paper in revised]
    assert calls["abstracts"] == [paper.abstract for paper in revised]
    assert missing.title not in calls["titles"]
