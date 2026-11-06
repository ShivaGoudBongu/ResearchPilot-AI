"""Streamlit app checks. These tests do not call OpenAlex or Gemini."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

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
    labels = [item.label for item in app.expander]
    assert any("Analysed paper" in label for label in labels)
    assert any("Paper without an abstract" in label for label in labels)
    assert len(app.link_button) == 2
    assert all(item.value == "View source" for item in app.link_button)

    visible = "\n".join(item.value for item in app.markdown)
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
