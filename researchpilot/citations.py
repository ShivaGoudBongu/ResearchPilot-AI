"""Deterministic APA 7 and general Harvard citations.

Formatting uses only the paper record. It never calls Gemini and never fills
in a journal, issue, page range, or date that OpenAlex did not provide.
Harvard here is a general style, not one institution's house style.
"""

from dataclasses import dataclass

from researchpilot.models import Paper

STYLE_APA = "apa"
STYLE_HARVARD = "harvard"
STYLE_OPTIONS = ("APA 7", "Harvard (general)")

_MISSING_AUTHORS = "authors"
_MISSING_YEAR = "year"
_MISSING_VENUE = "venue"
_MISSING_DOI = "DOI"

_PARTICLES = frozenset(
    {"van", "von", "de", "del", "da", "di", "der", "den", "la", "le", "st", "st."}
)
_SUFFIXES = {"jr": "Jr.", "sr": "Sr.", "ii": "II", "iii": "III", "iv": "IV"}


@dataclass(frozen=True)
class Citation:
    """One formatted reference and its in-text citation."""

    style: str
    reference: str
    in_text: str
    missing: tuple[str, ...]


@dataclass(frozen=True)
class _Name:
    surname: str
    initials: str
    suffix: str


def style_from_label(label: str) -> str:
    """Map the style names shown in the app to the formatter's codes."""
    if label == "Harvard (general)":
        return STYLE_HARVARD
    return STYLE_APA


def format_citation(paper: Paper, style: str) -> Citation:
    """Format one paper. Unknown styles raise ValueError."""
    if style not in (STYLE_APA, STYLE_HARVARD):
        raise ValueError(f"Unknown citation style: {style}")

    names = _authors(paper)
    year, year_missing = _year(paper)
    title = _title(paper)
    venue = _venue(paper)
    doi_url = normalize_doi_url(paper.doi)
    source_url = _http_url(paper.source_url)
    if doi_url and source_url and source_url.rstrip("/").lower() == doi_url.lower():
        source_url = None
    locator = doi_url or source_url

    missing = []
    if not names:
        missing.append(_MISSING_AUTHORS)
    if year_missing:
        missing.append(_MISSING_YEAR)
    if not venue:
        missing.append(_MISSING_VENUE)
    if not doi_url:
        missing.append(_MISSING_DOI)

    if style == STYLE_APA:
        reference = _apa_reference(names, year, title, venue, locator)
        in_text = _in_text(names, year, title, conjunction="&", quote_title=True)
    else:
        reference = _harvard_reference(names, year, title, venue, locator)
        in_text = _in_text(names, year, title, conjunction="and", quote_title=False)
    return Citation(style=style, reference=reference, in_text=in_text, missing=tuple(missing))


def format_reference_list(papers: list[Paper], style: str) -> str:
    """Alphabetise, dedupe, and join references for the current selection.

    Identity is the paper's existing stable key. The first copy wins.
    Papers with no author are sorted by title.
    """
    unique: list[Paper] = []
    seen: set[str] = set()
    for paper in papers:
        identity = paper.analysis_key()
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(paper)
    unique.sort(key=_sort_key)
    return "\n\n".join(format_citation(paper, style).reference for paper in unique)


def normalize_doi_url(value: str | None) -> str | None:
    """Return https://doi.org/10... or None when the value is not a DOI."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if lowered.startswith(prefix):
            suffix = text[len(prefix) :].strip().strip("/")
            if suffix.lower().startswith("10."):
                return "https://doi.org/" + suffix
            return None
    if lowered.startswith("doi:"):
        suffix = text[4:].strip().strip("/")
        if suffix.lower().startswith("10."):
            return "https://doi.org/" + suffix
        return None
    if lowered.startswith("10."):
        return "https://doi.org/" + text.strip().strip("/")
    return None


def _apa_reference(
    names: list[_Name],
    year: str,
    title: str,
    venue: str | None,
    locator: str | None,
) -> str:
    parts = []
    if names:
        parts.append(f"{_apa_authors(names)} ({year}).")
        parts.append(_sentence(title))
    else:
        parts.append(f"{_sentence(title)} ({year}).")
    if venue:
        parts.append(_sentence(venue))
    reference = " ".join(parts)
    if locator:
        reference = f"{reference} {locator}"
    return reference


def _harvard_reference(
    names: list[_Name],
    year: str,
    title: str,
    venue: str | None,
    locator: str | None,
) -> str:
    parts = []
    if names:
        parts.append(f"{_harvard_authors(names)} ({year})")
        parts.append(_sentence(title))
    else:
        parts.append(f"{_sentence(title)} ({year}).")
    if venue:
        parts.append(_sentence(venue))
    reference = " ".join(parts)
    if locator:
        reference = f"{reference} Available at: {locator}"
    return reference


def _apa_authors(names: list[_Name]) -> str:
    formatted = [_format_name(name) for name in names]
    if len(formatted) >= 21:
        return ", ".join(formatted[:19]) + ", ... " + formatted[-1]
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def _harvard_authors(names: list[_Name]) -> str:
    formatted = [_format_name(name) for name in names]
    if len(formatted) >= 4:
        return f"{formatted[0]} et al."
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + " and " + formatted[-1]


def _in_text(
    names: list[_Name],
    year: str,
    title: str,
    conjunction: str,
    quote_title: bool,
) -> str:
    if not names:
        short = _short_title(title)
        if quote_title:
            return f'("{short}", {year})'
        return f"({short}, {year})"
    surnames = [name.surname for name in names]
    if len(surnames) == 1:
        who = surnames[0]
    elif len(surnames) == 2:
        who = f"{surnames[0]} {conjunction} {surnames[1]}"
    else:
        who = f"{surnames[0]} et al."
    return f"({who}, {year})"


def _authors(paper: Paper) -> list[_Name]:
    parsed = []
    for raw in paper.authors:
        if not isinstance(raw, str):
            continue
        name = _parse_name(raw)
        if name is not None:
            parsed.append(name)
    return parsed


def _parse_name(display: str) -> _Name | None:
    """Invert a display name. OpenAlex does not provide given and family fields."""
    text = " ".join(display.split())
    if not text:
        return None
    if "," in text:
        return _parse_comma_name(text)
    return _parse_space_name(text)


def _parse_comma_name(text: str) -> _Name | None:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None
    surname = parts[0]
    rest = parts[1:]
    suffix = ""
    if rest:
        normalised = _suffix(rest[-1])
        if normalised:
            suffix = normalised
            rest = rest[:-1]
    return _Name(surname=surname, initials=_initials(" ".join(rest)), suffix=suffix)


def _parse_space_name(text: str) -> _Name | None:
    tokens = text.split()
    suffix = ""
    if len(tokens) > 1:
        normalised = _suffix(tokens[-1])
        if normalised:
            suffix = normalised
            tokens = tokens[:-1]
    if not tokens:
        return None
    surname, given = _split_surname(tokens)
    return _Name(surname=surname, initials=_initials(given), suffix=suffix)


def _split_surname(tokens: list[str]) -> tuple[str, str]:
    if len(tokens) == 1:
        return tokens[0], ""
    surname = [tokens[-1]]
    index = len(tokens) - 2
    while index >= 0 and tokens[index].lower() in _PARTICLES:
        surname.insert(0, tokens[index])
        index -= 1
    given_tokens = tokens[: index + 1]
    if not given_tokens:
        return " ".join(tokens), ""
    return " ".join(surname), " ".join(given_tokens)


def _suffix(token: str) -> str | None:
    return _SUFFIXES.get(token.lower().rstrip("."))


def _initials(given: str) -> str:
    pieces = []
    for token in given.split():
        letters = []
        for part in token.split("-"):
            letter = next((char for char in part if char.isalpha()), "")
            if letter:
                letters.append(letter.upper() + ".")
        if letters:
            pieces.append("-".join(letters))
    return " ".join(pieces)


def _format_name(name: _Name) -> str:
    text = f"{name.surname}, {name.initials}" if name.initials else name.surname
    if name.suffix:
        text = f"{text}, {name.suffix}"
    return text


def _year(paper: Paper) -> tuple[str, bool]:
    year = paper.publication_year
    if isinstance(year, int) and not isinstance(year, bool):
        return str(year), False
    return "n.d.", True


def _title(paper: Paper) -> str:
    if isinstance(paper.title, str) and paper.title.strip():
        return " ".join(paper.title.split())
    return "Untitled"


def _venue(paper: Paper) -> str | None:
    venue = getattr(paper, "venue", None)
    if isinstance(venue, str) and venue.strip():
        return " ".join(venue.split())
    return None


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower().startswith("https://") or text.lower().startswith("http://"):
        return text
    return None


def _sentence(text: str) -> str:
    if text[-1] in ".?!":
        return text
    return text + "."


def _short_title(title: str) -> str:
    words = title.split()
    if len(words) > 8:
        return " ".join(words[:6]) + "..."
    return title


def _sort_key(paper: Paper) -> tuple:
    names = _authors(paper)
    primary = names[0].surname.casefold() if names else _title(paper).casefold()
    year = paper.publication_year
    year_key = year if isinstance(year, int) and not isinstance(year, bool) else 10**9
    return (primary, year_key, _title(paper).casefold(), paper.analysis_key())
