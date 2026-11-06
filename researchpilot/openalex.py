"""Search the public OpenAlex Works API.

OpenAlex does not require an API key. An optional contact email can be
supplied with the OPENALEX_MAILTO environment variable so requests join
OpenAlex's polite pool. The email is never written into source code.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any

import requests

from researchpilot.abstracts import reconstruct_abstract
from researchpilot.models import Paper

_TAG_PATTERN = re.compile(r"<[^>]+>")
_USER_AGENT = "ResearchPilotAI/0.1 (phase-1 paper discovery; +https://openalex.org)"


class OpenAlexError(Exception):
    """A search could not be completed because the API call failed."""


class OpenAlexClient:
    """Small client for ``GET https://api.openalex.org/works``."""

    BASE_URL = "https://api.openalex.org/works"
    DEFAULT_TIMEOUT = 20.0
    MAX_RESULTS = 10
    # Ask only for the fields the app displays. primary_location also carries
    # the journal or venue name when OpenAlex has one. Volume, issue, and
    # pages are not requested.
    SELECT_FIELDS = ",".join(
        [
            "id",
            "doi",
            "ids",
            "title",
            "display_name",
            "publication_year",
            "authorships",
            "abstract_inverted_index",
            "primary_location",
            "open_access",
        ]
    )

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        mailto: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")
        self.timeout = timeout
        self.mailto = _clean_mailto(mailto)
        self._session = session or requests.Session()

    def search_papers(self, topic: str, limit: int = MAX_RESULTS) -> list[Paper]:
        """Return up to ``limit`` papers (maximum 10) for a research topic.

        Raises:
            ValueError: the topic is blank.
            OpenAlexError: the request timed out, the network failed, OpenAlex
                returned an HTTP error, or the body was not usable JSON.
        """
        query = (topic or "").strip()
        if not query:
            raise ValueError("Enter a research topic to search.")

        per_page = _clamp_limit(limit)
        params: dict[str, Any] = {
            "search": query,
            "per-page": per_page,
            "select": self.SELECT_FIELDS,
        }
        if self.mailto:
            params["mailto"] = self.mailto

        try:
            response = self._session.get(
                self.BASE_URL,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": _USER_AGENT,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise OpenAlexError(
                "OpenAlex took too long to respond. Check your connection and try again."
            ) from exc
        except requests.ConnectionError as exc:
            raise OpenAlexError(
                "Could not reach OpenAlex. Check your internet connection and try again."
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise OpenAlexError(
                f"OpenAlex returned an error (HTTP {status}). Please try again later."
            ) from exc
        except requests.RequestException as exc:
            raise OpenAlexError("The request to OpenAlex failed. Please try again.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAlexError("OpenAlex returned a response that was not valid JSON.") from exc

        return papers_from_payload(payload)


def papers_from_payload(payload: object) -> list[Paper]:
    """Parse a Works API JSON object into paper records."""
    if not isinstance(payload, dict):
        raise OpenAlexError("OpenAlex returned an unexpected response.")

    results = payload.get("results", [])
    if results is None:
        return []
    if not isinstance(results, list):
        raise OpenAlexError("OpenAlex returned an unexpected response.")

    papers: list[Paper] = []
    seen_openalex: set[str] = set()
    seen_dois: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        paper = parse_work(item)
        openalex_id = _identity(paper.openalex_id)
        doi = _doi_identity(paper.doi)
        if openalex_id and openalex_id in seen_openalex:
            continue
        if doi and doi in seen_dois:
            continue
        if openalex_id:
            seen_openalex.add(openalex_id)
        if doi:
            seen_dois.add(doi)
        papers.append(paper)
    return papers


def _identity(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower().rstrip("/")
    return text or None


def _doi_identity(value: str | None) -> str | None:
    text = _identity(value)
    if text is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip().rstrip("/")
    return text or None


def parse_work(work: dict) -> Paper:
    """Map one OpenAlex work object onto a Paper, tolerating missing fields."""
    title = _clean_display_text(work.get("title") or work.get("display_name")) or "Untitled"
    authors = _authors(work.get("authorships"))
    year = _parse_year(work.get("publication_year"))
    doi = _normalize_doi(work.get("doi")) or _normalize_doi(_nested(work.get("ids"), "doi"))
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    source_url = _source_url(work, doi)
    openalex_id = _http_url(work.get("id"))
    return Paper(
        title=title,
        authors=authors,
        publication_year=year,
        doi=doi,
        abstract=abstract,
        source_url=source_url,
        openalex_id=openalex_id,
        venue=_venue(work.get("primary_location")),
    )


def _clean_mailto(mailto: str | None) -> str | None:
    if mailto is None:
        mailto = os.environ.get("OPENALEX_MAILTO")
    if mailto is None:
        return None
    text = mailto.strip()
    return text or None


def _clamp_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("Result limit must be an integer.") from exc
    return max(1, min(value, OpenAlexClient.MAX_RESULTS))


def _authors(authorships: object) -> list[str]:
    if not isinstance(authorships, list):
        return []

    names: list[str] = []
    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        raw_name = author.get("display_name") if isinstance(author, dict) else None
        if not isinstance(raw_name, str) or not raw_name.strip():
            raw_name = authorship.get("raw_author_name")
        name = _clean_display_text(raw_name)
        if name:
            names.append(name)
    return names


def _parse_year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("https://doi.org/") or lowered.startswith("http://doi.org/"):
        return text
    if lowered.startswith("doi:"):
        text = text[4:].strip()
    if text.startswith("10."):
        return f"https://doi.org/{text}"
    return None


def _venue(location: object) -> str | None:
    source = _nested(location, "source")
    if not isinstance(source, dict):
        return None
    return _clean_display_text(source.get("display_name"))


def _source_url(work: dict, doi: str | None) -> str | None:
    location = work.get("primary_location")
    open_access = work.get("open_access")
    candidates = [
        _nested(location, "landing_page_url"),
        _nested(location, "pdf_url"),
        _nested(open_access, "oa_url"),
        doi,
        work.get("id"),
    ]
    for candidate in candidates:
        url = _http_url(candidate)
        if url:
            return url
    return None


def _nested(value: object, key: str) -> object:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("https://") or text.startswith("http://"):
        return text
    return None


def _clean_display_text(value: object) -> str | None:
    """Drop simple HTML tags OpenAlex sometimes leaves in titles."""
    if not isinstance(value, str):
        return None
    text = html.unescape(value)
    text = _TAG_PATTERN.sub("", text)
    text = " ".join(text.split())
    return text or None
