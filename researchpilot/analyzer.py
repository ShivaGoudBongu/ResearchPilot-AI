"""Analyse a paper title and abstract with Google Gemini.

The API key is read from the GEMINI_API_KEY environment variable.
python-dotenv loads a local .env file when this module is imported.
The key is never written into source code or included in error messages.
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ServerError

from researchpilot.models import Paper

load_dotenv()

MODEL_NAME = "gemini-3.5-flash-lite"

DISCLAIMER = (
    "AI-generated analysis based on the title and abstract only. "
    "Verify important claims against the full research paper."
)


class AnalysisError(Exception):
    """Gemini could not complete an analysis."""


def analyze_paper(title: str, abstract: str) -> str:
    """Return a four-part analysis of one paper.

    The model may use only the title and abstract. Missing objective,
    methodology, or findings stay "Not specified in the abstract". Limitations
    separate author-reported limits from labeled AI hypotheses.

    Raises:
        ValueError: the API key is missing, the abstract is blank, or Gemini
            returned no text.
        AnalysisError: the Gemini request failed, including rate limits and
            temporary server errors.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError(
            "GEMINI_API_KEY is missing. Add it to the .env file and restart the app."
        )

    abstract_text = abstract.strip() if isinstance(abstract, str) else ""
    if not abstract_text:
        raise ValueError("This paper has no abstract to analyse.")

    title_text = title.strip() if isinstance(title, str) and title.strip() else "Untitled"
    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=_prompt(title_text, abstract_text),
        )
    except APIError as exc:
        raise AnalysisError(_message_for_api_error(exc)) from exc
    except Exception as exc:
        raise AnalysisError("The analysis request failed. Please try again.") from exc

    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Gemini returned an empty response.")

    return text.strip()


_HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
_MAIN_SECTIONS = (
    "Research Objective",
    "Methodology",
    "Key Findings",
    "Limitations",
)
_MAIN_BY_NAME = {name.lower(): name for name in _MAIN_SECTIONS}
_SUBSECTIONS = {
    "author-reported limitations": "author_reported",
    "potential limitations to investigate": "potential",
}


def analysis_needs_request(stored: dict | None) -> bool:
    """Return whether Analyse with AI should call Gemini.

    A successful analysis is kept. A missing or failed analysis can be requested.
    """
    if not isinstance(stored, dict):
        return True
    return stored.get("status") != "ok"


def parse_analysis(text: str) -> dict | None:
    """Split a Gemini reply into the four sections and two limitation parts.

    Returns None when any of the four main headings is missing, so the page
    can show the original text unchanged.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    matches = list(_HEADING.finditer(text))
    if not matches:
        return None

    sections = {name: "" for name in _MAIN_SECTIONS}
    author_reported = None
    potential = None
    found: set[str] = set()

    for index, match in enumerate(matches):
        level = match.group(1)
        title = _heading_name(match.group(2))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if level == "##" and title in _MAIN_BY_NAME:
            name = _MAIN_BY_NAME[title]
            sections[name] = body
            found.add(name)
        elif level == "###" and title in _SUBSECTIONS:
            if _SUBSECTIONS[title] == "author_reported":
                author_reported = body
            else:
                potential = body

    if found != set(_MAIN_SECTIONS):
        return None
    return {
        "sections": sections,
        "author_reported": author_reported,
        "potential": potential,
    }


def _heading_name(value: str) -> str:
    cleaned = value.replace("*", "").strip().rstrip(":.")
    return cleaned.lower()


def retain_analyses(analyses: dict, papers: list[Paper]) -> dict:
    """Keep saved analyses only for papers in the current result list.

    Matching uses Paper.analysis_key(), so an analysis cannot reappear on a
    different paper that happens to occupy the same position.
    """
    if not analyses:
        return {}
    valid_keys = {paper.analysis_key() for paper in papers}
    return {key: value for key, value in analyses.items() if key in valid_keys}


def _prompt(title: str, abstract: str) -> str:
    return f"""You are a scientific research assistant.

Analyse the following paper using ONLY its title and abstract.

Paper title: {title}

Abstract: {abstract}

Provide exactly these four Markdown sections, in this order:

## Research Objective
## Methodology
## Key Findings
## Limitations

Under Limitations, use exactly these two subsections:

### Author-reported limitations
State only limitations the abstract explicitly reports. If it reports none, write "Not specified in the abstract."

### Potential limitations to investigate
Suggest at most three methodological concerns or unanswered questions grounded in the supplied abstract. Begin this subsection with: "These are AI-generated hypotheses, not findings reported by the authors." Do not present them as facts or as claims made by the authors.

Rules:
- Explain every section in simple academic English.
- For Research Objective, Methodology, and Key Findings, use only the title and abstract. If a point is absent, write "Not specified in the abstract."
- Do not invent datasets, sample sizes, results, experiments, or weaknesses.
- Ground every potential limitation in a specific detail from the supplied abstract.
- If the abstract is too thin for a meaningful hypothesis, write "The abstract does not provide enough information for a meaningful hypothesis." Do not add generic criticism.
- This is an abstract-based analysis, not a review of the full research paper.
"""


def _message_for_api_error(exc: APIError) -> str:
    code = exc.code
    if code == 429:
        return "Gemini is rate limiting requests. Wait a moment and try again."
    if code in (401, 403):
        return (
            "Gemini rejected the API key. Check GEMINI_API_KEY in the .env file "
            "and restart the app."
        )
    if isinstance(exc, ServerError) or (isinstance(code, int) and 500 <= code <= 599):
        return "Gemini is temporarily unavailable. Please try again later."
    return "Gemini could not analyse this abstract. Please try again."
