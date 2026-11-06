"""Streamlit interface for paper discovery and abstract analysis."""

import streamlit as st

from researchpilot.analyzer import (
    DISCLAIMER,
    AnalysisError,
    analysis_needs_request,
    analyze_paper,
    parse_analysis,
    retain_analyses,
)
from researchpilot.models import Paper
from researchpilot.openalex import OpenAlexClient, OpenAlexError

st.set_page_config(
    page_title="ResearchPilot AI",
    page_icon=":mag:",
    layout="centered",
)

st.title("ResearchPilot AI")
st.write(
    "Search OpenAlex for scientific papers, then analyse a selected abstract with Gemini. "
    "Each analysis covers the research objective, methodology, key findings, and limitations."
)


def _display(value: object) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, str) and not value.strip():
        return "Not available"
    return str(value)


def _doi_label(doi: str) -> str:
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.lower().startswith(prefix):
            return doi[len(prefix) :]
    return doi


def _author_summary(authors: list[str]) -> str:
    if not authors:
        return "Authors not available"
    if len(authors) <= 3:
        return ", ".join(authors)
    remaining = len(authors) - 3
    noun = "other" if remaining == 1 else "others"
    return f"{', '.join(authors[:3])}, and {remaining} {noun}"


def _has_abstract(paper: Paper) -> bool:
    return isinstance(paper.abstract, str) and bool(paper.abstract.strip())


def _summary_label(index: int, paper: Paper) -> str:
    year = _display(paper.publication_year)
    authors = _author_summary(paper.authors)
    return f"**{index}. {paper.title}** — {year} · {authors}"


def _render_analysis_text(text: str) -> None:
    st.markdown("**AI analysis**")
    st.caption(DISCLAIMER)
    parsed = parse_analysis(text)
    if parsed is None:
        st.markdown(text)
        return

    for name in ("Research Objective", "Methodology", "Key Findings"):
        st.markdown(f"**{name}**")
        st.write(_display(parsed["sections"].get(name)))

    st.markdown("**Limitations**")
    st.markdown("**Author-reported limitations**")
    author_reported = parsed["author_reported"]
    if author_reported is None:
        author_reported = parsed["sections"].get("Limitations")
    st.write(_display(author_reported) if _display(author_reported) != "Not available" else "Not specified in the abstract.")

    st.markdown("**Potential limitations to investigate**")
    st.caption(
        "These are AI-generated hypotheses, not established weaknesses or claims made by the authors."
    )
    potential = parsed["potential"]
    if not isinstance(potential, str) or not potential.strip():
        potential = "The abstract does not provide enough information for a meaningful hypothesis."
    st.write(potential)


def _render_stored_analysis(stored: dict) -> None:
    if stored.get("status") == "ok":
        _render_analysis_text(stored.get("text") or "")
        return
    if stored.get("message"):
        st.error(stored["message"])


def _analyse(paper: Paper) -> None:
    key = paper.analysis_key()
    if not analysis_needs_request(st.session_state.analyses.get(key)):
        return
    try:
        text = analyze_paper(title=paper.title, abstract=paper.abstract or "")
    except (ValueError, AnalysisError) as exc:
        st.session_state.analyses[key] = {"status": "error", "message": str(exc)}
        return
    st.session_state.analyses[key] = {"status": "ok", "text": text}


def _render_paper(index: int, paper: Paper) -> None:
    key = paper.analysis_key()
    with st.expander(_summary_label(index, paper), key=f"paper-{index}-{key}"):
        authors = ", ".join(paper.authors) if paper.authors else None
        st.markdown(f"**Authors:** {_display(authors)}")
        st.markdown(f"**Year:** {_display(paper.publication_year)}")
        if paper.doi:
            label = _doi_label(paper.doi)
            st.markdown(f"**DOI:** [{label}]({paper.doi})")
        else:
            st.markdown("**DOI:** Not available")
        st.markdown("**Abstract**")
        st.write(_display(paper.abstract))
        if paper.source_url:
            st.link_button(
                "View source",
                paper.source_url,
                key=f"source-{index}-{key}",
                help="Opens the article in a new tab.",
            )
        else:
            st.markdown("**Source URL:** Not available")

        stored = st.session_state.analyses.get(key)
        if _has_abstract(paper):
            if analysis_needs_request(stored):
                label = "Retry analysis" if stored and stored.get("status") == "error" else "Analyse with AI"
                if st.button(label, key=f"analyse-{index}-{key}"):
                    with st.spinner("Analysing the abstract with Gemini..."):
                        _analyse(paper)
                    stored = st.session_state.analyses.get(key)
        else:
            st.button("Analyse with AI", key=f"analyse-{index}-{key}", disabled=True)
            st.caption("This paper has no abstract, so AI analysis is unavailable.")

        if stored:
            _render_stored_analysis(stored)


def _search(topic: str) -> None:
    st.session_state.error = None
    st.session_state.papers = None
    st.session_state.searched_topic = topic.strip()
    if not topic.strip():
        st.session_state.error = "Enter a research topic to search."
        return

    with st.spinner("Searching OpenAlex..."):
        try:
            papers = OpenAlexClient().search_papers(topic)
        except OpenAlexError as exc:
            st.session_state.error = str(exc)
            return

    st.session_state.papers = papers
    st.session_state.analyses = retain_analyses(st.session_state.analyses, papers)


if "papers" not in st.session_state:
    st.session_state.papers = None
if "error" not in st.session_state:
    st.session_state.error = None
if "searched_topic" not in st.session_state:
    st.session_state.searched_topic = ""
if "analyses" not in st.session_state:
    st.session_state.analyses = {}

with st.container(border=True):
    with st.form("search_form"):
        topic = st.text_input(
            "Research topic",
            placeholder="e.g. graph neural networks for drug discovery",
        )
        submitted = st.form_submit_button("Search", type="primary")

if submitted:
    _search(topic)

if st.session_state.error:
    st.error(st.session_state.error)
elif st.session_state.papers is None:
    st.info("Enter a research topic and click Search.")
elif len(st.session_state.papers) == 0:
    st.warning(f'No papers found for "{st.session_state.searched_topic}". Try a broader topic.')
else:
    count = len(st.session_state.papers)
    noun = "paper" if count == 1 else "papers"
    st.success(f'{count} {noun} found for "{st.session_state.searched_topic}".')
    for index, paper in enumerate(st.session_state.papers, start=1):
        _render_paper(index, paper)
