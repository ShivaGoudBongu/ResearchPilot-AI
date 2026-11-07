"""Build Word reports from results ResearchPilot has already saved.

Export does not call Gemini and does not write report files to disk.
A comparison is exported only when its stored content key still matches
the papers and abstracts being exported.
"""

from datetime import date
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from researchpilot.analyzer import DISCLAIMER, parse_analysis
from researchpilot.citations import format_citation, format_reference_list
from researchpilot.comparison import SelectionError, comparison_cache_key, present_comparison
from researchpilot.models import Paper

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PAPER_REPORT_FILENAME = "researchpilot_paper_analysis.docx"
COMPARISON_REPORT_FILENAME = "researchpilot_comparison.docx"

_NOT_SPECIFIED = "Not specified in the abstract."
_INSUFFICIENT = "The abstract does not provide enough information for a meaningful hypothesis."
_NOT_A_REVIEW = (
    "This report repeats saved abstract-based output. "
    "It does not add findings. It is not a systematic literature review."
)
_INK = RGBColor(0x1F, 0x29, 0x37)


class ExportError(ValueError):
    """A stored result cannot be turned into a report."""


def paper_analysis_docx(
    paper: Paper,
    analysis_text: str,
    style: str,
    generated_on: date | None = None,
) -> bytes:
    """Return a Word report for one saved analysis of this paper."""
    if not isinstance(paper, Paper):
        raise ExportError("A paper analysis report needs one paper record.")
    if not isinstance(analysis_text, str) or not analysis_text.strip():
        raise ExportError("There is no saved analysis to export.")
    parsed = parse_analysis(analysis_text)
    if parsed is None:
        raise ExportError("This analysis cannot be exported because its sections are missing.")

    document = _new_document()
    _title(document, "ResearchPilot AI")
    _body(document, "Paper analysis report")
    _meta(document, "Generated", _format_date(generated_on or date.today()))
    _body(document, DISCLAIMER)
    _body(document, _NOT_A_REVIEW)
    _paper_metadata(document, paper)

    sections = parsed["sections"]
    _section(document, "Research objectives", _text(sections.get("Research Objective"), _NOT_SPECIFIED))
    _section(document, "Methodology", _text(sections.get("Methodology"), _NOT_SPECIFIED))
    _section(document, "Key findings", _text(sections.get("Key Findings"), _NOT_SPECIFIED))
    author_reported = parsed["author_reported"]
    if not isinstance(author_reported, str) or not author_reported.strip():
        author_reported = sections.get("Limitations")
    _section(document, "Author-reported limitations", _text(author_reported, _NOT_SPECIFIED))
    _heading(document, "AI-inferred potential limitations")
    _body(
        document,
        "These are AI-generated hypotheses, not established weaknesses or claims made by the authors.",
    )
    _body(document, _text(parsed["potential"], _INSUFFICIENT))

    citation = format_citation(paper, style)
    _heading(document, "Reference")
    _body(document, citation.reference)
    if citation.missing:
        _body(
            document,
            "Check before use: " + ", ".join(citation.missing) + " missing. Nothing was filled in.",
        )
    return _save(document)


def comparison_docx(
    papers: list[Paper] | tuple[Paper, ...],
    cached: dict,
    style: str,
    generated_on: date | None = None,
) -> bytes:
    """Return a Word report for a comparison cached for these exact papers.

    The cache content key includes the abstract text. A saved comparison for
    different papers, or the same papers with changed abstracts, is refused.
    """
    if not isinstance(cached, dict) or cached.get("status") != "ok":
        raise ExportError("There is no completed comparison to export.")
    try:
        current_key = comparison_cache_key(papers)
    except SelectionError as exc:
        raise ExportError("There is no completed comparison to export.") from exc
    if cached.get("content_key") != current_key:
        raise ExportError("This comparison does not match the current paper selection.")
    view = present_comparison(cached.get("result"), papers)

    document = _new_document()
    _title(document, "ResearchPilot AI")
    _body(document, "Comparison report")
    _meta(document, "Generated", _format_date(generated_on or date.today()))
    _body(document, view["disclaimer"])
    _body(document, _NOT_A_REVIEW)

    _heading(document, "Selected papers")
    for index, paper in enumerate(papers, start=1):
        title = paper.title.strip() if isinstance(paper.title, str) and paper.title.strip() else "Untitled"
        _body(document, f"{index}. {title}")
        _meta(document, "Authors", _authors(paper))
        _meta(document, "Year", _year(paper))
        _meta(document, "Paper identifier", paper.analysis_key())

    for section in view["sections"]:
        _heading(document, section["label"])
        if section["key"] == "author_reported_gaps":
            _body(document, "Taken from wording in the selected abstracts. Not independently verified.")
        elif section["kind"] == "ai_inferred":
            _body(
                document,
                "AI-inferred hypotheses from the selected abstracts, "
                "not gaps reported by the authors and not independently verified.",
            )
        for claim in section["claims"]:
            _body(document, claim["text"])
            attribution = _attribution(claim)
            if attribution:
                _body(document, attribution)

    _heading(document, "References")
    references = format_reference_list(list(papers), style)
    if not references:
        raise ExportError("There are no references to export.")
    for reference in references.split("\n\n"):
        _body(document, reference)
    return _save(document)


def _new_document() -> Document:
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.font.color.rgb = _INK
    for section in document.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        header = section.header.paragraphs[0]
        header.text = ""
        header_run = header.add_run("ResearchPilot AI")
        header_run.bold = True
        header_run.font.name = "Times New Roman"
        header_run.font.size = Pt(10)
        footer = section.footer.paragraphs[0]
        footer.text = ""
        footer_run = footer.add_run("Abstract-based report. Not a systematic literature review. ")
        footer_run.font.name = "Times New Roman"
        footer_run.font.size = Pt(9)
        _append_page_number(footer)
    return document


def _append_page_number(paragraph) -> None:
    run = paragraph.add_run()
    run.font.name = "Times New Roman"
    run.font.size = Pt(9)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)


def _title(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(18)
    run.font.color.rgb = _INK


def _heading(document: Document, text: str) -> None:
    paragraph = document.add_heading(text, level=1)
    for run in paragraph.runs:
        run.font.name = "Times New Roman"
        run.font.size = Pt(14)
        run.font.color.rgb = _INK


def _body(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)
    paragraph.paragraph_format.space_after = Pt(8)


def _meta(document: Document, label: str, value: str) -> None:
    paragraph = document.add_paragraph()
    label_run = paragraph.add_run(f"{label}: ")
    label_run.bold = True
    label_run.font.name = "Times New Roman"
    label_run.font.size = Pt(12)
    value_run = paragraph.add_run(value)
    value_run.font.name = "Times New Roman"
    value_run.font.size = Pt(12)
    paragraph.paragraph_format.space_after = Pt(2)


def _section(document: Document, heading: str, text: str) -> None:
    _heading(document, heading)
    _body(document, text)


def _paper_metadata(document: Document, paper: Paper) -> None:
    _heading(document, "Paper")
    title = paper.title.strip() if isinstance(paper.title, str) and paper.title.strip() else "Untitled"
    _meta(document, "Title", title)
    _meta(document, "Authors", _authors(paper))
    _meta(document, "Year", _year(paper))
    if isinstance(paper.venue, str) and paper.venue.strip():
        _meta(document, "Venue", " ".join(paper.venue.split()))
    doi = paper.doi.strip() if isinstance(paper.doi, str) and paper.doi.strip() else ""
    source = paper.source_url.strip() if isinstance(paper.source_url, str) and paper.source_url.strip() else ""
    _meta(document, "DOI", doi or "Not available")
    if source and source.rstrip("/").lower() != doi.rstrip("/").lower():
        _meta(document, "Source URL", source)
    elif not doi:
        _meta(document, "Source URL", "Not available")
    _meta(document, "Paper identifier", paper.analysis_key())


def _authors(paper: Paper) -> str:
    names = [name.strip() for name in paper.authors if isinstance(name, str) and name.strip()]
    return ", ".join(names) if names else "Not available"


def _year(paper: Paper) -> str:
    year = paper.publication_year
    if isinstance(year, int) and not isinstance(year, bool):
        return str(year)
    return "Not available"


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _attribution(claim: dict) -> str:
    titles = claim.get("paper_titles") or []
    identifiers = claim.get("paper_ids") or []
    if not titles and not identifiers:
        return "AI-generated from the selected abstracts."
    parts = []
    for index, title in enumerate(titles):
        identifier = identifiers[index] if index < len(identifiers) else ""
        parts.append(f"{title} ({identifier})" if identifier else str(title))
    for identifier in identifiers[len(titles) :]:
        parts.append(str(identifier))
    return "Papers: " + "; ".join(parts)


def _format_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _save(document: Document) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
