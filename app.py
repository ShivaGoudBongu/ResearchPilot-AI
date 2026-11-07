"""Streamlit interface for paper discovery, analysis, and comparison."""

import hashlib
import os

import streamlit as st

from researchpilot.analyzer import (
    DISCLAIMER,
    AnalysisError,
    analysis_needs_request,
    analyze_paper,
    parse_analysis,
    retain_analyses,
)
from researchpilot.citations import format_citation, format_reference_list, style_from_label
from researchpilot.export import (
    COMPARISON_REPORT_FILENAME,
    DOCX_MIME,
    PAPER_REPORT_FILENAME,
    ExportError,
    comparison_docx,
    paper_analysis_docx,
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
from researchpilot.usage import (
    ANALYSIS_REQUEST_LIMIT,
    COMPARISON_REQUEST_LIMIT,
    analysis_request_is_outgoing,
    comparison_request_is_outgoing,
    record_outgoing_request,
    remaining_requests,
    request_allowed,
)

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
PREVIEW_LENGTH = 420

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


def _summary_label(index: int, paper: Paper) -> str:
    year = _display(paper.publication_year)
    authors = _author_summary(paper.authors)
    return f"**{index}. {paper.title}** — {year} · {authors}"


def _mark_card() -> None:
    st.markdown('<div class="rp-card"></div>', unsafe_allow_html=True)


def _preview(abstract: str) -> str:
    text = " ".join(abstract.split())
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[:PREVIEW_LENGTH].rstrip() + "…"


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


def _gemini_configured() -> bool:
    """Return whether a key is present, without storing or displaying it."""
    value = os.getenv("GEMINI_API_KEY")
    return isinstance(value, str) and bool(value.strip())


def _analyse(paper: Paper) -> None:
    key = paper.analysis_key()
    stored = st.session_state.analyses.get(key)
    if not analysis_needs_request(stored) or not _has_abstract(paper):
        return
    if not request_allowed(st.session_state.gemini_analysis_requests, ANALYSIS_REQUEST_LIMIT):
        return
    if analysis_request_is_outgoing(stored, True, _gemini_configured()):
        st.session_state.gemini_analysis_requests = record_outgoing_request(
            st.session_state.gemini_analysis_requests
        )
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
    if not request_allowed(st.session_state.gemini_comparison_requests, COMPARISON_REQUEST_LIMIT):
        return
    cached_status = None if cached is None else cached[1].get("status")
    counted = comparison_request_is_outgoing(True, cached_status, _gemini_configured())
    if counted:
        st.session_state.gemini_comparison_requests = record_outgoing_request(
            st.session_state.gemini_comparison_requests
        )
    try:
        with st.spinner("Comparing the selected abstracts with Gemini..."):
            result = compare_papers(selected)
    except SelectionError as exc:
        if counted:
            st.session_state.gemini_comparison_requests = max(
                0, st.session_state.gemini_comparison_requests - 1
            )
        st.session_state.comparisons[content_key] = {
            "status": "error",
            "message": str(exc),
            "content_key": content_key,
        }
        return
    except (ValueError, AnalysisError, ComparisonError) as exc:
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


def _render_analysis_download(paper: Paper, stored: dict, style: str) -> None:
    if stored.get("status") != "ok":
        return
    text = stored.get("text")
    if not isinstance(text, str) or not text.strip():
        return
    try:
        payload = paper_analysis_docx(paper, text, style)
    except ExportError:
        st.caption("A Word report is not available because this analysis is missing the expected sections.")
        return
    digest = hashlib.sha256(f"{style}|{text}".encode("utf-8")).hexdigest()[:12]
    st.download_button(
        "Download Word Report",
        data=payload,
        file_name=PAPER_REPORT_FILENAME,
        mime=DOCX_MIME,
        key=f"download-analysis-{digest}-{paper.analysis_key()}",
        help="Downloads the saved analysis as a Word document. This does not call Gemini.",
    )


def _render_comparison_download(selected: list[Paper], cached: dict, style: str) -> None:
    try:
        payload = comparison_docx(selected, cached, style)
    except (ExportError, ComparisonError, SelectionError):
        return
    digest = hashlib.sha256(
        f"{style}|{cached.get('content_key')}".encode("utf-8")
    ).hexdigest()[:12]
    st.download_button(
        "Download Word Report",
        data=payload,
        file_name=COMPARISON_REPORT_FILENAME,
        mime=DOCX_MIME,
        key=f"download-comparison-{digest}",
        help="Downloads the saved comparison as a Word document. This does not call Gemini.",
    )


def _render_comparison(selected: list[Paper], style: str) -> None:
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
    _render_comparison_download(selected, cached, style)


def _render_source(paper: Paper) -> None:
    if paper.doi:
        label = _doi_label(paper.doi)
        st.markdown(f"**DOI:** [{label}]({paper.doi})")
    else:
        st.markdown("**DOI:** Not available")
    if paper.source_url:
        st.link_button(
            "View source",
            paper.source_url,
            help="Opens the article in a new tab.",
        )
    else:
        st.markdown("**Source URL:** Not available")


def _citation_style() -> str:
    choice = st.selectbox(
        "Citation style",
        ("APA 7", "Harvard (general)"),
        key="citation_style",
        help="Harvard (general) is a general style, not one institution's variant.",
    )
    return style_from_label(str(choice))


def _render_citation(index: int, paper: Paper, style: str) -> None:
    citation = format_citation(paper, style)
    with st.expander("Citation"):
        if citation.missing:
            st.caption(
                "Check before use: "
                + ", ".join(citation.missing)
                + " missing. Nothing was filled in."
            )
        st.text_area(
            "Reference",
            value=citation.reference,
            height=68,
            key=_citation_key("ref", index, paper, style, citation.reference),
            help="Select the reference and copy it.",
        )
        st.text_area(
            "In-text citation",
            value=citation.in_text,
            height=68,
            key=_citation_key("in", index, paper, style, citation.in_text),
            help="Select the in-text citation and copy it.",
        )


def _render_reference_list(selected: list[Paper], style: str) -> None:
    st.subheader("Reference list")
    st.caption(
        "Built from the papers selected now, using OpenAlex metadata only. "
        "It is not checked by Gemini."
    )
    text = format_reference_list(selected, style)
    if not text:
        st.info("Select papers on Discover Papers. This list only includes the current selection.")
        return
    digest = hashlib.sha256(f"{style}|{text}".encode("utf-8")).hexdigest()[:16]
    st.text_area(
        "References",
        value=text,
        height=180,
        key=f"reference-list-{digest}",
        help="Select the list and copy it. It changes with the selection and the citation style.",
    )


def _citation_key(kind: str, index: int, paper: Paper, style: str, text: str) -> str:
    search_id = st.session_state.get("search_id", 0)
    token = hashlib.sha256(f"{style}|{text}|{paper.analysis_key()}".encode("utf-8")).hexdigest()[:12]
    return f"cite-{kind}-{search_id}-{index}-{token}"


def _render_paper(index: int, paper: Paper, style: str) -> None:
    key = paper.analysis_key()
    title = paper.title.strip() if isinstance(paper.title, str) and paper.title.strip() else "Untitled"
    with st.container(border=True):
        _mark_card()
        st.markdown(_summary_label(index, paper))
        if _has_abstract(paper):
            _restore_selection(index, paper)
            st.checkbox(
                "Select for comparison",
                key=_selection_widget_key(index, paper),
            )
            _render_source(paper)
            st.markdown("**Abstract**")
            abstract = paper.abstract or ""
            preview = _preview(abstract)
            st.write(preview)
            if preview != " ".join(abstract.split()):
                with st.expander("Full abstract"):
                    st.write(abstract)
            _render_analysis_action(index, paper, key)
        else:
            st.caption(f'"{title}" has no abstract, so it cannot be selected for comparison.')
            _render_source(paper)
            st.button("Analyse with AI", key=f"analyse-{index}-{key}", disabled=True)
            st.caption("This paper has no abstract, so AI analysis is unavailable.")
        _render_citation(index, paper, style)


def _render_analysis_action(index: int, paper: Paper, key: str) -> None:
    stored = st.session_state.analyses.get(key)
    if analysis_needs_request(stored):
        blocked = not request_allowed(
            st.session_state.gemini_analysis_requests, ANALYSIS_REQUEST_LIMIT
        )
        label = "Retry analysis" if stored and stored.get("status") == "error" else "Analyse with AI"
        if st.button(label, key=f"analyse-{index}-{key}", disabled=blocked):
            with st.spinner("Analysing the abstract with Gemini..."):
                _analyse(paper)
            stored = st.session_state.analyses.get(key)
        if blocked:
            st.caption(
                "This browser session has used its 5 paper analyses. "
                "Saved analyses remain available. This is not an account quota."
            )
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
    with st.container(border=True):
        _mark_card()
        with st.form("search_form"):
            topic = st.text_input(
                "Research topic",
                placeholder="e.g. graph neural networks for drug discovery",
                key="topic_query",
            )
            submitted = st.form_submit_button("Search", type="primary")
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
    st.success(f'{count} {noun} found for "{st.session_state.searched_topic}".')
    style = _citation_style()
    for index, paper in enumerate(papers, start=1):
        _render_paper(index, paper, style)
    selected = _selected_papers(papers)
    _render_selection_status(selected)
    st.caption("Open Compare Research when 3 to 5 papers are selected.")


def _analysis_can_export(stored: object) -> bool:
    return (
        isinstance(stored, dict)
        and stored.get("status") == "ok"
        and isinstance(stored.get("text"), str)
        and bool(stored.get("text").strip())
    )


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
    exportable = any(_analysis_can_export(st.session_state.analyses.get(paper.analysis_key())) for paper in papers)
    style = _citation_style() if exportable else style_from_label("APA 7")
    for index, paper in enumerate(papers, start=1):
        stored = st.session_state.analyses.get(paper.analysis_key())
        if not isinstance(stored, dict):
            continue
        shown = True
        with st.container(border=True):
            _mark_card()
            st.markdown(_summary_label(index, paper))
            authors = ", ".join(paper.authors) if paper.authors else None
            st.markdown(f"**Authors:** {_display(authors)}")
            st.markdown(f"**Year:** {_display(paper.publication_year)}")
            _render_source(paper)
            _render_stored_analysis(stored)
            _render_analysis_download(paper, stored, style)
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

    style = _citation_style()
    _render_reference_list(selected, style)

    served = False
    found = _cached_comparison(selected)
    if found is not None and found[1].get("status") == "ok":
        served = True
    comparison_blocked = (
        not served
        and not selection_errors(selected)
        and not request_allowed(st.session_state.gemini_comparison_requests, COMPARISON_REQUEST_LIMIT)
    )
    if st.button(
        "Compare Selected Papers",
        key="compare-selected",
        type="primary",
        disabled=bool(selection_errors(selected)) or comparison_blocked,
    ):
        _compare(selected)
    if comparison_blocked:
        st.caption(
            "This browser session has used its 2 comparisons. "
            "A saved comparison for the current papers remains available. "
            "This is not an account quota."
        )
    _render_comparison(selected, style)


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
        st.title("ResearchPilot AI")
        st.caption("AI-Powered Research Assistant")
        page = st.radio("Sections", PAGES, key="nav_section")
        st.caption("Built with Python, Streamlit, OpenAlex & Gemini AI.")
        analyses_left = remaining_requests(
            st.session_state.gemini_analysis_requests, ANALYSIS_REQUEST_LIMIT
        )
        comparisons_left = remaining_requests(
            st.session_state.gemini_comparison_requests, COMPARISON_REQUEST_LIMIT
        )
        st.caption(
            f"Gemini this session: {analyses_left} of {ANALYSIS_REQUEST_LIMIT} analyses "
            f"and {comparisons_left} of {COMPARISON_REQUEST_LIMIT} comparisons remaining. "
            "This limit applies only to this browser session."
        )
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
if "gemini_analysis_requests" not in st.session_state:
    st.session_state.gemini_analysis_requests = 0
if "gemini_comparison_requests" not in st.session_state:
    st.session_state.gemini_comparison_requests = 0

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
