"""Select papers and compare their abstracts with one Gemini request."""

from __future__ import annotations

import hashlib
import json

from researchpilot.analyzer import generate_text
from researchpilot.models import Paper

MIN_PAPERS = 3
MAX_PAPERS = 5


class SelectionError(ValueError):
    """The selected papers cannot be compared."""


def selection_errors(papers: object) -> list[str]:
    """Return user-facing reasons a selection cannot be compared.

    An empty list means the selection is valid: 3 to 5 distinct papers,
    each with an abstract and a usable stable identifier.
    """
    if not isinstance(papers, (list, tuple)):
        return ["Select 3 to 5 papers to compare."]

    errors: list[str] = []
    count = len(papers)
    if count < MIN_PAPERS:
        errors.append("Select at least 3 papers to compare.")
    elif count > MAX_PAPERS:
        errors.append("Select at most 5 papers to compare.")

    identifiers: list[str] = []
    for paper in papers:
        identifier = _identifier(paper)
        if identifier is None:
            errors.append("A selected item is not a paper with a usable identifier.")
            continue
        identifiers.append(identifier)
        if not _has_abstract(paper):
            errors.append(f'"{_label(paper)}" has no abstract, so it cannot be compared.')

    if len(identifiers) != len(set(identifiers)):
        errors.append(
            "Two or more selected papers share the same identifier, "
            "so they cannot be compared separately."
        )
    return errors


def validate_selection(papers: object) -> None:
    """Raise SelectionError when the papers cannot be compared."""
    errors = selection_errors(papers)
    if errors:
        raise SelectionError("\n".join(errors))


def selection_key(papers: list[Paper] | tuple[Paper, ...]) -> str:
    """Return a deterministic identity for this exact set of papers.

    The key is a JSON list of sorted ``analysis_key()`` values. Order of
    selection does not matter. Card position and Python ``hash()`` are not used.
    """
    validate_selection(papers)
    identifiers = sorted(_identifier(paper) for paper in papers)
    return json.dumps(identifiers, ensure_ascii=False, separators=(",", ":"))


def comparison_cache_key(papers: list[Paper] | tuple[Paper, ...]) -> str:
    """Identity of a comparison, including the abstract text that produced it.

    The same paper identifiers with a different abstract do not match. Order
    does not matter.
    """
    validate_selection(papers)
    entries = [
        {"id": _identifier(paper), "abstract": _abstract_token(paper)}
        for paper in papers
    ]
    entries.sort(key=lambda item: item["id"])
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def retain_comparisons(stored: object, papers: list[Paper] | tuple[Paper, ...]) -> dict:
    """Keep saved comparisons whose papers and abstracts are still current.

    An entry is kept only when every stored identifier is still present with
    the same abstract hash. A matching identifier with a changed or missing
    abstract is dropped, so a new search cannot show an outdated comparison.
    """
    if not isinstance(stored, dict) or not stored:
        return {}
    current: dict[str, str] = {}
    for paper in papers:
        identifier = _identifier(paper)
        if identifier and _has_abstract(paper):
            current[identifier] = _abstract_token(paper)
    kept = {}
    for key, value in stored.items():
        entries = _content_entries(key)
        if entries and all(current.get(identifier) == digest for identifier, digest in entries):
            kept[key] = value
    return kept


def _abstract_token(paper: Paper) -> str:
    text = " ".join(paper.abstract.split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_entries(key: object) -> list[tuple[str, str]] | None:
    if not isinstance(key, str) or not key.strip():
        return None
    try:
        parsed = json.loads(key)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    entries: list[tuple[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        identifier = item.get("id")
        digest = item.get("abstract")
        if not isinstance(identifier, str) or not identifier.strip():
            return None
        if not isinstance(digest, str) or len(digest) != 64:
            return None
        entries.append((identifier.strip(), digest))
    return entries


def comparison_matches_selection(stored: object, papers: object) -> bool:
    """Return whether a saved comparison is for this exact selection.

    An invalid selection never matches, even if a comparison was stored earlier.
    """
    stored_key = _stored_key(stored)
    if stored_key is None:
        return False
    try:
        return stored_key == selection_key(papers)  # type: ignore[arg-type]
    except SelectionError:
        return False


def _stored_key(stored: object) -> str | None:
    if isinstance(stored, str):
        text = stored.strip()
        return text or None
    if isinstance(stored, dict):
        value = stored.get("selection_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _identifier(paper: object) -> str | None:
    if not isinstance(paper, Paper):
        return None
    key = paper.analysis_key()
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def _has_abstract(paper: Paper) -> bool:
    return isinstance(paper.abstract, str) and bool(paper.abstract.strip())


def _label(paper: Paper) -> str:
    title = paper.title.strip() if isinstance(paper.title, str) else ""
    return title or "Untitled"


COMPARISON_SCOPE = (
    "This comparison uses only the selected abstracts. "
    "It cannot establish a research gap across the entire literature."
)
PRESENTATION_DISCLAIMER = (
    "AI-generated comparison based only on the selected titles and abstracts. "
    "Verify claims against the full papers. "
    "This comparison cannot establish gaps across the entire research literature."
)
NOT_REPORTED_GAP = "Not reported in the supplied abstracts."
NOT_SPECIFIED_LIMITATION = "Not specified in the supplied abstracts."
INSUFFICIENT_HYPOTHESIS = (
    "The abstracts do not provide enough information for a meaningful hypothesis."
)
_SECTIONS = (
    "research_objectives",
    "methodologies",
    "key_findings",
    "author_reported_limitations",
    "author_reported_gaps",
    "ai_inferred_gaps",
)
_DISPLAY_SECTIONS = (
    ("research_objectives", "Research Objectives", "comparison"),
    ("methodologies", "Methodologies", "comparison"),
    ("key_findings", "Key Findings", "comparison"),
    ("author_reported_limitations", "Author-Reported Limitations", "author_reported"),
    ("author_reported_gaps", "Author-Reported Research Gaps", "author_reported"),
    ("ai_inferred_gaps", "AI-Inferred Potential Research Gaps", "ai_inferred"),
)
_EMPTY_SECTION = NOT_SPECIFIED_LIMITATION


class ComparisonError(ValueError):
    """Gemini returned a comparison that cannot be used."""


def compare_papers(papers: list[Paper] | tuple[Paper, ...]) -> dict:
    """Compare 3 to 5 papers with one Gemini request.

    The selection is validated before the API key is read or a request is sent.
    The returned dictionary includes ``selection_key`` and is returned only
    when every required section is present and every cited identifier belongs
    to the selection.

    Raises:
        SelectionError: the papers fail Step 1 validation.
        ValueError: the API key is missing or Gemini returned no text.
        AnalysisError: the Gemini request failed.
        ComparisonError: the response is malformed, incomplete, or cites an
            unselected paper.
    """
    validate_selection(papers)
    raw_text = generate_text(_comparison_prompt(papers))
    parsed = parse_comparison(raw_text, papers)
    return {
        "selection_key": selection_key(papers),
        "scope": COMPARISON_SCOPE,
        **parsed,
    }


def present_comparison(result: object, papers: list[Paper] | tuple[Paper, ...]) -> dict:
    """Turn a validated comparison into labelled sections for display.

    Titles are taken only from the supplied papers, matched by
    ``analysis_key()``. A result for a different selection is rejected.
    The disclaimer is fixed and does not come from the model text.
    """
    if not comparison_matches_selection(result, papers):
        raise ComparisonError("This comparison does not match the current paper selection.")
    if not isinstance(result, dict):
        raise ComparisonError("This comparison does not match the current paper selection.")

    titles_by_id = _titles_by_identifier(papers)
    sections = []
    for key, label, kind in _DISPLAY_SECTIONS:
        raw_claims = result.get(key) or []
        if not isinstance(raw_claims, list):
            raise ComparisonError(f"Gemini returned a malformed {key} section.")
        if key in {"author_reported_limitations", "author_reported_gaps"}:
            raw_claims = [item for item in raw_claims if not _is_reported_absence(key, item)]
        claims = (
            [_empty_display_claim(key)]
            if not raw_claims
            else [_present_claim(item, titles_by_id) for item in raw_claims]
        )
        sections.append({"key": key, "label": label, "kind": kind, "claims": claims})

    return {
        "selection_key": result.get("selection_key"),
        "disclaimer": PRESENTATION_DISCLAIMER,
        "sections": sections,
    }


def parse_comparison(text: str, papers: list[Paper] | tuple[Paper, ...]) -> dict:
    """Parse and validate a comparison JSON document for these papers."""
    validate_selection(papers)
    allowed = {_identifier(paper) for paper in papers}
    try:
        payload = json.loads(_json_text(text))
    except json.JSONDecodeError as exc:
        raise ComparisonError("Gemini returned a comparison that was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ComparisonError("Gemini returned a comparison that was not valid JSON.")

    missing = [name for name in _SECTIONS if name not in payload]
    if missing:
        joined = ", ".join(missing)
        raise ComparisonError(
            f"Gemini returned a comparison that is missing required sections: {joined}."
        )

    return {name: _parse_claims(name, payload[name], allowed) for name in _SECTIONS}


def _comparison_prompt(papers: list[Paper] | tuple[Paper, ...]) -> str:
    blocks = []
    for paper in papers:
        blocks.append(
            "\n".join(
                [
                    f"Paper identifier: {_identifier(paper)}",
                    f"Title: {_label(paper)}",
                    f"Abstract: {paper.abstract.strip()}",
                ]
            )
        )
    papers_text = "\n\n".join(blocks)
    return f"""You are a scientific research assistant.

Compare ONLY the supplied paper titles and abstracts. {COMPARISON_SCOPE}

{papers_text}

Return one JSON object and no other text. Use exactly these fields:
research_objectives, methodologies, key_findings, author_reported_limitations, author_reported_gaps, ai_inferred_gaps.

Each field is a list of objects with:
- claim: a string
- paper_ids: a list of paper identifiers copied exactly from the Paper identifier lines above

Rules:
- Every substantive claim must cite one or more selected paper identifiers in paper_ids.
- research_objectives, methodologies, and key_findings must each contain at least one claim.
- author_reported_limitations may contain only limitations explicitly stated in the abstracts. A statement that limitations are absent is not a limitation and must not cite papers. If none are stated, return one object: {{"claim": "{NOT_SPECIFIED_LIMITATION}", "paper_ids": []}}.
- author_reported_gaps may contain only gaps explicitly stated in the abstracts. A statement that gaps are absent is not a gap and must not cite papers. If none are stated, return one object: {{"claim": "{NOT_REPORTED_GAP}", "paper_ids": []}}.
- ai_inferred_gaps are AI-generated hypotheses, not findings reported by the authors. Cite the abstracts they are grounded in. Return at most three. If the abstracts are too thin, return one object: {{"claim": "{INSUFFICIENT_HYPOTHESIS}", "paper_ids": []}}.
- Do not invent datasets, sample sizes, experiments, results, citations, or claims that are not supported by the supplied abstracts.
- Do not cite a paper identifier that was not supplied above.
- Do not name, cite, or attribute an objective, method, or finding to any paper that was not supplied above.
- Describe only the supplied abstracts. For objectives, methods, and findings, if a point is absent, say that it is not reported in the supplied abstracts. Do not present a claim as a conclusion about the full papers or the wider research literature.
- Do not write unqualified statements such as "None of the studies evaluate...". Write "None of the supplied abstracts report..." instead.
"""


def _parse_claims(name: str, value: object, allowed: set[str]) -> list[dict]:
    if not isinstance(value, list):
        raise ComparisonError(f"Gemini returned a malformed {name} section.")
    if name == "author_reported_limitations" and not value:
        return [{"claim": NOT_SPECIFIED_LIMITATION, "paper_ids": []}]
    if name == "author_reported_gaps" and not value:
        return [{"claim": NOT_REPORTED_GAP, "paper_ids": []}]
    if name == "ai_inferred_gaps" and not value:
        return [{"claim": INSUFFICIENT_HYPOTHESIS, "paper_ids": []}]
    if not value:
        raise ComparisonError(
            "Gemini returned a comparison that is missing required sections: "
            f"{name}."
        )

    claims: list[dict] = []
    for item in value:
        claims.append(_parse_claim(name, item, allowed))

    if name == "author_reported_limitations":
        cited = [claim for claim in claims if claim["paper_ids"]]
        if not cited:
            return [{"claim": NOT_SPECIFIED_LIMITATION, "paper_ids": []}]
        return cited
    if name == "author_reported_gaps":
        cited = [claim for claim in claims if claim["paper_ids"]]
        if not cited:
            return [{"claim": NOT_REPORTED_GAP, "paper_ids": []}]
        return cited
    if name == "ai_inferred_gaps":
        cited = [claim for claim in claims if claim["paper_ids"]]
        if not cited:
            return [{"claim": INSUFFICIENT_HYPOTHESIS, "paper_ids": []}]
        return cited
    return claims


def _parse_claim(name: str, item: object, allowed: set[str]) -> dict:
    if not isinstance(item, dict):
        raise ComparisonError("Gemini returned an incomplete comparison.")
    claim = item.get("claim")
    raw_ids = item.get("paper_ids")
    if not isinstance(claim, str) or not claim.strip():
        raise ComparisonError("Gemini returned an incomplete comparison.")
    if not isinstance(raw_ids, list):
        raise ComparisonError("Gemini returned an incomplete comparison.")

    paper_ids: list[str] = []
    for paper_id in raw_ids:
        if not isinstance(paper_id, str) or not paper_id.strip():
            raise ComparisonError("Gemini returned an incomplete comparison.")
        identifier = paper_id.strip()
        if identifier not in allowed:
            raise ComparisonError(
                "Gemini cited a paper that was not in the selected set."
            )
        if identifier not in paper_ids:
            paper_ids.append(identifier)

    text = claim.strip()
    if name == "author_reported_limitations" and _is_absence_statement(text):
        return {"claim": NOT_SPECIFIED_LIMITATION, "paper_ids": []}
    if name == "author_reported_gaps" and (_is_absence_statement(text) or _is_explicit_absence(text)):
        return {"claim": NOT_REPORTED_GAP, "paper_ids": []}
    if paper_ids:
        return {"claim": text, "paper_ids": paper_ids}
    if name == "ai_inferred_gaps" and _is_insufficient(text):
        return {"claim": INSUFFICIENT_HYPOTHESIS, "paper_ids": []}
    raise ComparisonError(
        "Gemini returned a comparison claim that does not cite a selected paper."
    )


def _is_reported_absence(section_key: str, item: object) -> bool:
    if not isinstance(item, dict):
        return False
    claim = item.get("claim")
    if not isinstance(claim, str):
        return False
    if _is_absence_statement(claim):
        return True
    return section_key == "author_reported_gaps" and _is_explicit_absence(claim)


def _is_absence_statement(claim: str) -> bool:
    """Return whether a sentence says the abstracts do not contain the evidence."""
    lowered = " ".join(claim.lower().split())
    markers = (
        "do not explicitly",
        "does not explicitly",
        "did not explicitly",
        "not explicitly report",
        "not explicitly state",
        "not explicitly specify",
        "none of the supplied abstracts",
        "none of the abstracts",
        "no limitations are",
        "no limitation is",
        "no explicit limitation",
        "limitations are not reported",
        "limitations are not specified",
        "limitations are not stated",
        "limitation is not reported",
        "gaps are not reported",
        "gap is not reported",
        "no research gap",
        "no gaps are reported",
        "not reported in the supplied abstracts",
        "not specified in the supplied abstracts",
        "not stated in the supplied abstracts",
    )
    return any(marker in lowered for marker in markers)


def _is_explicit_absence(claim: str) -> bool:
    lowered = claim.lower()
    return "not reported" in lowered or "not specified" in lowered or "not stated" in lowered


def _is_insufficient(claim: str) -> bool:
    lowered = claim.lower()
    return "not enough information" in lowered or "too thin" in lowered or "meaningful hypothesis" in lowered


def _present_claim(item: object, titles_by_id: dict[str, str]) -> dict:
    if not isinstance(item, dict):
        raise ComparisonError("A comparison claim is incomplete.")
    text = item.get("claim")
    raw_ids = item.get("paper_ids", [])
    if not isinstance(text, str) or not text.strip():
        raise ComparisonError("A comparison claim is incomplete.")
    if not isinstance(raw_ids, list):
        raise ComparisonError("A comparison claim is incomplete.")

    paper_ids: list[str] = []
    paper_titles: list[str] = []
    for paper_id in raw_ids:
        if not isinstance(paper_id, str) or not paper_id.strip():
            raise ComparisonError("A comparison claim is incomplete.")
        identifier = paper_id.strip()
        title = titles_by_id.get(identifier)
        if title is None:
            raise ComparisonError(
                "A comparison claim cites a paper that is not in the current selection."
            )
        if identifier not in paper_ids:
            paper_ids.append(identifier)
            paper_titles.append(title)

    return {
        "text": text.strip(),
        "paper_ids": paper_ids,
        "paper_titles": paper_titles,
        "ai_generated": True,
        "based_on": "abstracts",
    }


def _empty_display_claim(section_key: str) -> dict:
    if section_key == "author_reported_gaps":
        text = NOT_REPORTED_GAP
    elif section_key == "ai_inferred_gaps":
        text = INSUFFICIENT_HYPOTHESIS
    else:
        text = _EMPTY_SECTION
    return {
        "text": text,
        "paper_ids": [],
        "paper_titles": [],
        "ai_generated": True,
        "based_on": "abstracts",
        "empty": True,
    }


def _titles_by_identifier(papers: list[Paper] | tuple[Paper, ...]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for paper in papers:
        identifier = _identifier(paper)
        if identifier:
            titles[identifier] = _label(paper)
    return titles


def _json_text(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
