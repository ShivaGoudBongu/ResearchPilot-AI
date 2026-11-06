"""Citation formatting uses paper metadata and never invents the rest."""

import inspect

import pytest

from researchpilot.citations import (
    STYLE_APA,
    STYLE_HARVARD,
    format_citation,
    format_reference_list,
    normalize_doi_url,
    style_from_label,
)
from researchpilot.models import Paper

TITLE = "Graph neural networks for drug discovery"
VENUE = "Nature Machine Intelligence"
DOI = "https://doi.org/10.1000/example"
ABSTRACT = "Models represent molecules. This sentence must not be cited."


def _paper(**overrides) -> Paper:
    values = {
        "title": TITLE,
        "authors": ["Ada Lovelace", "Alan Turing", "Grace Hopper"],
        "publication_year": 2024,
        "doi": DOI,
        "abstract": ABSTRACT,
        "source_url": "https://publisher.example/paper",
        "openalex_id": "https://openalex.org/W1",
        "venue": VENUE,
    }
    values.update(overrides)
    return Paper(**values)


def test_apa_and_harvard_format_one_two_and_three_authors():
    three = format_citation(_paper(), STYLE_APA)
    assert three.reference == (
        "Lovelace, A., Turing, A., & Hopper, G. (2024). "
        "Graph neural networks for drug discovery. "
        "Nature Machine Intelligence. https://doi.org/10.1000/example"
    )
    assert three.in_text == "(Lovelace et al., 2024)"
    assert three.missing == ()

    harvard_three = format_citation(_paper(), STYLE_HARVARD)
    assert harvard_three.reference == (
        "Lovelace, A., Turing, A. and Hopper, G. (2024) "
        "Graph neural networks for drug discovery. "
        "Nature Machine Intelligence. Available at: https://doi.org/10.1000/example"
    )
    assert harvard_three.in_text == "(Lovelace et al., 2024)"

    two_authors = ["Ada Lovelace", "Alan Turing"]
    apa_two = format_citation(_paper(authors=two_authors), STYLE_APA)
    harvard_two = format_citation(_paper(authors=two_authors), STYLE_HARVARD)
    assert apa_two.reference.startswith("Lovelace, A., & Turing, A. (2024).")
    assert apa_two.in_text == "(Lovelace & Turing, 2024)"
    assert harvard_two.reference.startswith("Lovelace, A. and Turing, A. (2024)")
    assert harvard_two.in_text == "(Lovelace and Turing, 2024)"

    apa_one = format_citation(_paper(authors=["Ada Lovelace"]), STYLE_APA)
    harvard_one = format_citation(_paper(authors=["Ada Lovelace"]), STYLE_HARVARD)
    assert apa_one.reference.startswith("Lovelace, A. (2024).")
    assert apa_one.in_text == "(Lovelace, 2024)"
    assert harvard_one.reference.startswith("Lovelace, A. (2024)")
    assert harvard_one.in_text == "(Lovelace, 2024)"


def test_long_author_lists_follow_apa_and_general_harvard_rules():
    four = [f"Ann Person{index:02d}" for index in range(1, 5)]
    harvard = format_citation(_paper(authors=four), STYLE_HARVARD)
    apa = format_citation(_paper(authors=four), STYLE_APA)

    assert harvard.reference.startswith("Person01, A. et al. (2024)")
    assert "Person02" not in harvard.reference
    assert harvard.in_text == "(Person01 et al., 2024)"
    assert apa.reference.startswith("Person01, A., Person02, A., Person03, A., & Person04, A. (2024).")
    assert apa.in_text == "(Person01 et al., 2024)"

    twenty_one = [f"Ann Person{index:02d}" for index in range(1, 22)]
    long_apa = format_citation(_paper(authors=twenty_one), STYLE_APA)
    assert "Person01, A." in long_apa.reference
    assert "Person19, A." in long_apa.reference
    assert "Person21, A." in long_apa.reference
    assert "Person20" not in long_apa.reference
    assert "..." in long_apa.reference
    assert "&" not in long_apa.reference
    assert long_apa.in_text == "(Person01 et al., 2024)"


def test_missing_metadata_is_flagged_and_not_invented():
    no_author = format_citation(_paper(authors=[]), STYLE_APA)
    assert no_author.missing == ("authors",)
    assert no_author.reference.startswith(
        "Graph neural networks for drug discovery. (2024). Nature Machine Intelligence."
    )
    assert no_author.in_text == '("Graph neural networks for drug discovery", 2024)'

    long_title = "One two three four five six seven eight nine"
    shortened = format_citation(_paper(authors=[], title=long_title), STYLE_HARVARD)
    assert shortened.in_text == "(One two three four five six..., 2024)"
    assert long_title in shortened.reference

    no_year = format_citation(_paper(publication_year=None, authors=["Ada Lovelace"]), STYLE_APA)
    assert "year" in no_year.missing
    assert "(n.d.)." in no_year.reference
    assert no_year.in_text == "(Lovelace, n.d.)"
    assert "2024" not in no_year.reference

    no_venue = format_citation(_paper(venue=None, authors=["Ada Lovelace"]), STYLE_APA)
    assert no_venue.missing == ("venue",)
    assert no_venue.reference == (
        "Lovelace, A. (2024). Graph neural networks for drug discovery. "
        "https://doi.org/10.1000/example"
    )
    assert VENUE not in no_venue.reference

    no_doi = format_citation(_paper(doi=None, authors=["Ada Lovelace"]), STYLE_HARVARD)
    assert "DOI" in no_doi.missing
    assert no_doi.reference.endswith("Available at: https://publisher.example/paper")
    assert "doi.org" not in no_doi.reference

    bare = format_citation(
        _paper(
            authors=[],
            publication_year=None,
            venue=None,
            doi=None,
            source_url=None,
            title="Only a title",
        ),
        STYLE_APA,
    )
    assert bare.missing == ("authors", "year", "venue", "DOI")
    assert bare.reference == "Only a title. (n.d.)."
    assert ABSTRACT not in bare.reference
    for invented in ("Vol.", "pp.", "Issue", "Unknown", "Nature"):
        assert invented not in bare.reference


def test_doi_values_are_normalised_without_treating_other_urls_as_dois():
    assert normalize_doi_url("doi:10.1000/ABC/") == "https://doi.org/10.1000/ABC"
    assert normalize_doi_url("http://dx.doi.org/10.5555/xyz") == "https://doi.org/10.5555/xyz"
    assert normalize_doi_url("HTTPS://DOI.ORG/10.1000/Example") == "https://doi.org/10.1000/Example"
    assert normalize_doi_url("https://publisher.example/10.1000/example") is None

    citation = format_citation(
        _paper(doi="http://doi.org/10.1000/example/", source_url="http://doi.org/10.1000/example/"),
        STYLE_APA,
    )
    assert citation.reference.endswith("https://doi.org/10.1000/example")
    assert citation.reference.count("https://doi.org/10.1000/example") == 1
    assert "DOI" not in citation.missing


def test_special_characters_and_name_forms_are_preserved():
    citation = format_citation(
        _paper(
            title="BERT, AT&T and naïve models?",
            authors=["José García-López", "Mary-Jane Watson", "Ludwig van Beethoven"],
            venue="Études",
        ),
        STYLE_APA,
    )
    assert citation.reference.startswith(
        "García-López, J., Watson, M.-J., & van Beethoven, L. (2024). "
        "BERT, AT&T and naïve models? Études."
    )
    assert citation.in_text == "(García-López et al., 2024)"

    suffix = format_citation(_paper(authors=["Martin Luther King Jr."]), STYLE_APA)
    assert suffix.reference.startswith("King, M. L., Jr. (2024).")
    assert suffix.in_text == "(King, 2024)"

    comma_form = format_citation(_paper(authors=["Müller, François"]), STYLE_HARVARD)
    assert comma_form.reference.startswith("Müller, F. (2024)")
    apostrophe = format_citation(_paper(authors=["Cathy O'Neil"]), STYLE_APA)
    assert apostrophe.reference.startswith("O'Neil, C. (2024).")


def test_reference_lists_sort_and_deduplicate_by_stable_identity():
    first = _paper(title="Zebra study", authors=["Ada Lovelace"], openalex_id="https://openalex.org/W1")
    duplicate = _paper(title="Alpha duplicate", authors=["Grace Hopper"], openalex_id="https://openalex.org/W1")
    early = _paper(title="Early Lovelace", authors=["Ada Lovelace"], publication_year=2010, openalex_id="https://openalex.org/W2")
    missing_author = _paper(
        title="Aardvark notes",
        authors=[],
        publication_year=2019,
        openalex_id="https://openalex.org/W3",
        venue=None,
        doi=None,
    )
    same_doi = _paper(
        title="First DOI title",
        authors=["Alan Turing"],
        doi="https://doi.org/10.1000/same",
        openalex_id=None,
    )
    same_doi_again = _paper(
        title="Second DOI title",
        authors=["Grace Hopper"],
        doi="https://doi.org/10.1000/same",
        openalex_id=None,
    )

    text = format_reference_list(
        [first, duplicate, early, missing_author, same_doi, same_doi_again],
        STYLE_HARVARD,
    )

    assert "Alpha duplicate" not in text
    assert "Second DOI title" not in text
    assert text.index("Aardvark notes") < text.index("Early Lovelace")
    assert text.index("Early Lovelace") < text.index("Zebra study")
    assert text.index("Zebra study") < text.index("First DOI title")
    assert "Turing, A." in text
    assert "Available at:" in text
    assert " & " not in text
    assert format_reference_list([], STYLE_APA) == ""


def test_formatter_does_not_use_gemini_or_an_unknown_style():
    source = inspect.getsource(inspect.getmodule(format_citation))
    assert "google" not in source
    assert "analyze_paper" not in source
    assert "compare_papers" not in source
    with pytest.raises(ValueError):
        format_citation(_paper(), "mla")
    assert style_from_label("Harvard (general)") == STYLE_HARVARD
    assert style_from_label("APA 7") == STYLE_APA
