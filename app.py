"""Streamlit interface for paper discovery, analysis, and comparison."""

import html

import streamlit as st

from researchpilot.analyzer import (
    DISCLAIMER,
    AnalysisError,
    analysis_needs_request,
    analyze_paper,
    parse_analysis,
    retain_analyses,
)
from researchpilot.comparison import (
    PRESENTATION_DISCLAIMER,
    ComparisonError,
    SelectionError,
    compare_papers,
    comparison_cache_key,
    present_comparison,
    retain_comparisons,
    selection_errors,
)
from researchpilot.models import Paper
from researchpilot.openalex import OpenAlexClient, OpenAlexError
from researchpilot.theme import inject_theme

PAGE_DISCOVER = "Discover Papers"
PAGE_ANALYSIS = "AI Paper Analysis"
PAGE_COMPARE = "Compare Research"
PAGE_ABOUT = "About Project"
PAGES = (PAGE_DISCOVER, PAGE_ANALYSIS, PAGE_COMPARE, PAGE_ABOUT)
SUGGESTIONS = (
    "Explainable AI",
    "Fraud Detection",
    "Machine Learning",
    "Large Language Models",
)
GITHUB_URL = "https://github.com/ShivaGoudBongu/ResearchPilot-AI"
PREVIEW_LENGTH = 320

st.set_page_config(
    page_title="ResearchPilot AI",
    page_icon=":material/menu_book:",
    layout="wide",
)
inject_theme()


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


def _paper_title(paper: Paper) -> str:
    if isinstance(paper.title, str) and paper.title.strip():
        return paper.title.strip()
    return "Untitled"


def _short_label(title: str, limit: int = 72) -> str:
    text = " ".join(title.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _paper_heading(index: int, paper: Paper) -> str:
    title = _paper_title(paper)
    st.markdown(f"**{index}. {title}**")
    st.caption(f"{_display(paper.publication_year)} · {_author_summary(paper.authors)}")
    return title


def _mark_card(missing: bool = False) -> None:
    kind = "rp-card rp-missing" if missing else "rp-card"
    st.markdown(f'<div class="{kind}"></div>', unsafe_allow_html=True)


def _preview_text(abstract: str) -> tuple[str, bool]:
    text = " ".join(abstract.split())
    if len(text) <= PREVIEW_LENGTH:
        return text, False
    return text[:PREVIEW_LENGTH].rstrip() + "…", True


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


def _selection_widget_key(index: int, paper: Paper) -> str:
    search_id = st.session_state.get("search_id", 0)
    return f"select-{search_id}-{index}-{paper.analysis_key()}"


def _selection_memory_key(index: int, paper: Paper) -> str:
    return f"picked-{_selection_widget_key(index, paper)}"


def _restore_selection(index: int, paper: Paper) -> None:
    """Put a saved choice back before the checkbox is created.

    Streamlit drops a checkbox value after the control leaves the page.
    The picked- copy is what Compare Research reads.
    """
    widget_key = _selection_widget_key(index, paper)
    memory_key = _selection_memory_key(index, paper)
    if widget_key not in st.session_state and memory_key in st.session_state:
        st.session_state[widget_key] = bool(st.session_state[memory_key])


def _selected_papers(papers: list[Paper]) -> list[Paper]:
    selected = []
    for index, paper in enumerate(papers, start=1):
        if not _has_abstract(paper):
            continue
        widget_key = _selection_widget_key(index, paper)
        memory_key = _selection_memory_key(index, paper)
        if widget_key in st.session_state:
            chosen = bool(st.session_state.get(widget_key))
            st.session_state[memory_key] = chosen
        else:
            chosen = bool(st.session_state.get(memory_key))
        if chosen:
            selected.append(paper)
    return selected


def _clear_comparison_selection() -> None:
    for state_key in list(st.session_state.keys()):
        if isinstance(state_key, str) and (
            state_key.startswith("select-") or state_key.startswith("picked-")
        ):
            del st.session_state[state_key]


def _cached_comparison(selected: list[Paper]) -> tuple[str, dict] | None:
    if selection_errors(selected):
        return None
    content_key = comparison_cache_key(selected)
    cached = st.session_state.comparisons.get(content_key)
    if not isinstance(cached, dict) or cached.get("content_key") != content_key:
        return None
    return content_key, cached


def _compare(selected: list[Paper]) -> None:
    if selection_errors(selected):
        return
    content_key = comparison_cache_key(selected)
    cached = _cached_comparison(selected)
    if cached is not None and cached[1].get("status") == "ok":
        return
    try:
        with st.spinner("Comparing the selected abstracts with Gemini..."):
            result = compare_papers(selected)
    except (SelectionError, ValueError, AnalysisError, ComparisonError) as exc:
        st.session_state.comparisons[content_key] = {
            "status": "error",
            "message": str(exc),
            "content_key": content_key,
        }
        return
    st.session_state.comparisons[content_key] = {
        "status": "ok",
        "result": result,
        "selection_key": result.get("selection_key"),
        "content_key": content_key,
    }


def _render_comparison(selected: list[Paper]) -> None:
    found = _cached_comparison(selected)
    if found is None:
        return
    content_key, cached = found
    if not isinstance(cached, dict):
        return
    if cached.get("status") == "error":
        st.error(cached.get("message") or "The comparison failed. Please try again.")
        return
    if cached.get("status") != "ok":
        return

    try:
        view = present_comparison(cached.get("result"), selected)
    except ComparisonError as exc:
        st.session_state.comparisons[content_key] = {
            "status": "error",
            "message": str(exc),
            "selection_key": cached.get("selection_key"),
            "content_key": content_key,
        }
        st.error(str(exc))
        return

    st.subheader("Comparison")
    st.caption(PRESENTATION_DISCLAIMER)
    for section in view["sections"]:
        st.markdown(f"**{section['label']}**")
        if section["key"] == "author_reported_gaps":
            st.caption(
                "Taken from wording in the selected abstracts. Not independently verified."
            )
        elif section["kind"] == "ai_inferred":
            st.caption(
                "AI-inferred hypotheses from the selected abstracts, "
                "not gaps reported by the authors and not independently verified."
            )
        for claim in section["claims"]:
            st.write(claim["text"])
            titles = claim.get("paper_titles") or []
            if titles:
                st.caption(
                    "AI-generated from the selected abstracts. Papers: " + "; ".join(titles)
                )
            else:
                st.caption("AI-generated from the selected abstracts.")


def _render_doi(paper: Paper) -> None:
    if not paper.doi:
        return
    label = html.escape(_doi_label(paper.doi))
    href = html.escape(paper.doi, quote=True)
    st.markdown(
        f'<p class="rp-meta">DOI: <a href="{href}">{label}</a></p>',
        unsafe_allow_html=True,
    )


def _render_source_action(paper: Paper, index: int, title: str) -> None:
    if paper.source_url:
        st.link_button(
            "View source",
            paper.source_url,
            help=f"Opens the source for {index}. {title} in a new tab.",
            use_container_width=True,
        )
        return
    st.caption(f"No source link is available for {index}. {title}.")


def _render_paper(index: int, paper: Paper) -> None:
    key = paper.analysis_key()
    with st.container(border=True):
        if _has_abstract(paper):
            _mark_card()
            title = _paper_heading(index, paper)
            _render_doi(paper)
            abstract = paper.abstract or ""
            preview, truncated = _preview_text(abstract)
            st.markdown(
                f'<p class="rp-preview">{html.escape(preview)}</p>',
                unsafe_allow_html=True,
            )
            if truncated:
                with st.expander(f"Full abstract {index}: {_short_label(title)}"):
                    st.write(abstract)
            st.markdown('<hr class="rp-actions">', unsafe_allow_html=True)
            _restore_selection(index, paper)
            st.checkbox(
                "Select for comparison",
                key=_selection_widget_key(index, paper),
                help=f"Select {index}. {title} for comparison.",
            )
            _render_source_action(paper, index, title)
            _render_analysis_action(index, paper, key, title)
        else:
            _mark_card(missing=True)
            title = _paper_heading(index, paper)
            st.caption(f'"{title}" has no abstract, so it cannot be selected for comparison.')
            _render_doi(paper)
            st.markdown('<hr class="rp-actions">', unsafe_allow_html=True)
            _render_source_action(paper, index, title)
            st.button(
                "Analyse with AI",
                key=f"analyse-{index}-{key}",
                disabled=True,
                help=(
                    f"This paper has no abstract, so AI analysis is unavailable for {index}. {title}."
                ),
                use_container_width=True,
            )
            st.caption("This paper has no abstract, so AI analysis is unavailable.")


def _render_analysis_action(index: int, paper: Paper, key: str, title: str) -> None:
    stored = st.session_state.analyses.get(key)
    if analysis_needs_request(stored):
        label = "Retry analysis" if stored and stored.get("status") == "error" else "Analyse with AI"
        if st.button(
            label,
            key=f"analyse-{index}-{key}",
            help=f"{label} for {index}. {title}.",
            use_container_width=True,
        ):
            with st.spinner("Analysing the abstract with Gemini..."):
                _analyse(paper)
            stored = st.session_state.analyses.get(key)
    if stored and stored.get("status") == "error":
        st.error(stored.get("message") or "The analysis failed. Please try again.")
    elif stored and stored.get("status") == "ok":
        st.caption("Analysis saved. Open AI Paper Analysis to read it.")


def _render_selection_status(selected: list[Paper]) -> None:
    selected_count = len(selected)
    st.caption(f"{selected_count} papers selected. A comparison needs 3 to 5 papers.")
    errors = selection_errors(selected)
    if selected and errors:
        st.caption(errors[0])


def _queue_example(topic: str) -> None:
    st.session_state["topic_query"] = topic
    st.session_state["queued_search"] = topic


def _render_search_form() -> str | None:
    st.title("Discover research. Understand faster.")
    st.markdown(
        '<p class="rp-lead">Search academic literature, explore AI-powered insights, '
        "and compare scientific studies.</p>",
        unsafe_allow_html=True,
    )
    with st.form("search_form"):
        topic = st.text_input(
            "Research topic",
            placeholder="e.g. graph neural networks for drug discovery",
            key="topic_query",
        )
        submitted = st.form_submit_button("Search", type="primary", use_container_width=True)
    with st.container():
        st.markdown('<div class="rp-examples"></div>', unsafe_allow_html=True)
        st.caption("Examples")
        columns = st.columns(2)
        for index, label in enumerate(SUGGESTIONS):
            with columns[index % 2]:
                st.button(
                    label,
                    key=f"example-{label}",
                    on_click=_queue_example,
                    args=(label,),
                    use_container_width=True,
                )
    if submitted:
        return topic
    return None


def _render_discover(papers: list[Paper] | None) -> None:
    if papers is None:
        if not st.session_state.error:
            st.info("Enter a research topic and click Search.")
        return
    if len(papers) == 0:
        st.warning(f'No papers found for "{st.session_state.searched_topic}". Try a broader topic.')
        return

    count = len(papers)
    noun = "paper" if count == 1 else "papers"
    st.markdown(f'**Results for “{st.session_state.searched_topic}”**')
    st.caption(f"{count} {noun}")
    for index, paper in enumerate(papers, start=1):
        _render_paper(index, paper)
    selected = _selected_papers(papers)
    _render_selection_status(selected)
    st.caption("Open Compare Research when 3 to 5 papers are selected.")


def _render_analysis_page(papers: list[Paper] | None) -> None:
    st.title("AI Paper Analysis")
    st.markdown(
        '<p class="rp-lead">Author-reported limitations are taken from the abstract. '
        "Potential limitations are AI hypotheses, not statements made by the authors.</p>",
        unsafe_allow_html=True,
    )
    if st.session_state.error or not papers:
        st.info(
            "Search for papers on Discover Papers, then choose Analyse with AI "
            "on a paper that has an abstract. The result appears here."
        )
        return

    shown = False
    for index, paper in enumerate(papers, start=1):
        stored = st.session_state.analyses.get(paper.analysis_key())
        if not isinstance(stored, dict):
            continue
        shown = True
        with st.container(border=True):
            _mark_card()
            title = _paper_heading(index, paper)
            _render_doi(paper)
            _render_source_action(paper, index, title)
            _render_stored_analysis(stored)
    if not shown:
        st.info(
            "No analysis yet. On Discover Papers, choose Analyse with AI "
            "on a paper that has an abstract."
        )


def _render_compare_page(papers: list[Paper] | None) -> None:
    st.title("Compare Research")
    st.markdown(
        '<p class="rp-lead">Compare 3 to 5 selected abstracts. '
        "The report cannot establish a research gap across the entire literature.</p>",
        unsafe_allow_html=True,
    )
    if st.session_state.error or not papers:
        st.info(
            "Search for papers on Discover Papers, then select 3 to 5 papers "
            "that include an abstract."
        )
        return

    selected = _selected_papers(papers)
    _render_selection_status(selected)
    if selected:
        st.markdown("**Selected papers**")
        for paper in selected:
            title = paper.title.strip() if isinstance(paper.title, str) and paper.title.strip() else "Untitled"
            st.markdown(f"- {title}")
    else:
        st.caption("No papers are selected yet. Select them on Discover Papers.")

    reasons = selection_errors(selected)
    if st.button(
        "Compare Selected Papers",
        key="compare-selected",
        type="primary",
        disabled=bool(reasons),
        help=reasons[0] if reasons else "Compare the selected paper abstracts.",
    ):
        _compare(selected)
    _render_comparison(selected)


def _render_about() -> None:
    st.title("ResearchPilot AI")
    st.markdown(
        "An AI-powered academic research assistant developed using Python, "
        "Streamlit, OpenAlex and Google Gemini."
    )
    st.subheader("Features")
    st.markdown(
        "\n".join(
            [
                "- Academic paper discovery.",
                "- AI-assisted abstract analysis.",
                "- Multi-paper comparison.",
                "- Potential research-gap exploration.",
                "- Evidence-aware research summaries.",
            ]
        )
    )
    st.subheader("Technology")
    st.markdown(
        "\n".join(
            [
                "- Python",
                "- Streamlit",
                "- OpenAlex API",
                "- Google Gemini API",
                "- Pytest",
            ]
        )
    )
    st.subheader("Repository")
    st.markdown(f"[ResearchPilot AI on GitHub]({GITHUB_URL})")
    st.info(
        "ResearchPilot analyses available abstracts. "
        "It is not a replacement for reading the full scientific papers."
    )


def _search(topic: str) -> None:
    st.session_state.error = None
    st.session_state.papers = None
    st.session_state.searched_topic = topic.strip()
    st.session_state.search_id = int(st.session_state.get("search_id", 0)) + 1
    _clear_comparison_selection()
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
    st.session_state.comparisons = retain_comparisons(st.session_state.comparisons, papers)


def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown('<p class="rp-brand">ResearchPilot AI</p>', unsafe_allow_html=True)
        st.caption("AI-Powered Research Assistant")
        page = st.radio("Sections", PAGES, key="nav_section")
        st.markdown('<div class="rp-side-foot"></div>', unsafe_allow_html=True)
        st.caption("Built with Python, Streamlit, OpenAlex & Gemini AI.")
    return page


if "papers" not in st.session_state:
    st.session_state.papers = None
if "error" not in st.session_state:
    st.session_state.error = None
if "searched_topic" not in st.session_state:
    st.session_state.searched_topic = ""
if "analyses" not in st.session_state:
    st.session_state.analyses = {}
if "comparisons" not in st.session_state:
    st.session_state.comparisons = {}
if "search_id" not in st.session_state:
    st.session_state.search_id = 0

page = _render_sidebar()
queued = st.session_state.pop("queued_search", None)
submitted_topic = _render_search_form() if page == PAGE_DISCOVER else None
search_topic = queued if queued else submitted_topic
if search_topic is not None:
    _search(search_topic)

if st.session_state.error:
    st.error(st.session_state.error)

papers = st.session_state.papers
if page == PAGE_ANALYSIS:
    _render_analysis_page(papers)
elif page == PAGE_COMPARE:
    _render_compare_page(papers)
elif page == PAGE_ABOUT:
    _render_about()
else:
    _render_discover(papers)
