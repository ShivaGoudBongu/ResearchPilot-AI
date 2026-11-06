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

    def analysis_key(self) -> str:
        """Stable identity for a saved AI analysis.

        OpenAlex id is preferred, then DOI. Title and year are only a
        fallback, so a result is never matched by its position on the page.
        """
        openalex_id = _present(self.openalex_id)
        if openalex_id:
            return f"openalex:{openalex_id}"
        doi = _present(self.doi)
        if doi:
            return f"doi:{doi}"
        year = "unknown" if self.publication_year is None else str(self.publication_year)
        return f"title:{self.title}|year:{year}"


def _present(value: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
