"""Data returned for one scientific paper."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Paper:
    """A paper record ready for display.

    Missing OpenAlex fields stay None (or an empty author list) so the
    interface can say "Not available" instead of inventing values.
    """

    title: str
    authors: list[str]
    publication_year: int | None
    doi: str | None
    abstract: str | None
    source_url: str | None
    openalex_id: str | None = None
