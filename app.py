"""Streamlit interface for Phase 1 paper discovery."""

import streamlit as st

from researchpilot.openalex import OpenAlexClient, OpenAlexError

st.set_page_config(
    page_title="ResearchPilot AI",
    page_icon=":mag:",
    layout="centered",
)

st.title("ResearchPilot AI")
st.caption(
    "Phase 1 — search OpenAlex for scientific papers on a research topic. "
    "This version does not use a language model."
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


def _render_paper(index: int, paper) -> None:
    with st.container(border=True):
        st.subheader(f"{index}. {paper.title}")
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
            st.link_button("View source", paper.source_url)
        else:
            st.markdown("**Source URL:** Not available")


def _search(topic: str) -> None:
    st.session_state.error = None
    st.session_state.papers = None
    st.session_state.searched_topic = topic.strip()
    if not topic.strip():
        st.session_state.error = "Enter a research topic to search."
        return

    with st.spinner("Searching OpenAlex..."):
        try:
            st.session_state.papers = OpenAlexClient().search_papers(topic)
        except OpenAlexError as exc:
            st.session_state.error = str(exc)


if "papers" not in st.session_state:
    st.session_state.papers = None
if "error" not in st.session_state:
    st.session_state.error = None
if "searched_topic" not in st.session_state:
    st.session_state.searched_topic = ""

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
    st.success(f'Found {count} {noun} for "{st.session_state.searched_topic}".')
    for index, paper in enumerate(st.session_state.papers, start=1):
        _render_paper(index, paper)
