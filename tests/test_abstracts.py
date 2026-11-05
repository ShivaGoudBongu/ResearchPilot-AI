"""Tests for OpenAlex inverted-index abstract reconstruction."""

from researchpilot.abstracts import reconstruct_abstract


def test_reconstruct_places_words_in_position_order():
    inverted = {
        "networks": [2],
        "Graph": [0],
        "neural": [1],
        "learn": [3],
        "structure.": [6],
        "graph": [5],
        "from": [4],
    }

    assert (
        reconstruct_abstract(inverted)
        == "Graph neural networks learn from graph structure."
    )


def test_reconstruct_repeats_a_word_at_each_position():
    inverted = {"in": [1, 3], "Words": [0], "order": [2], "matter.": [4]}

    assert reconstruct_abstract(inverted) == "Words in order in matter."


def test_reconstruct_returns_none_for_missing_or_empty_input():
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None
    assert reconstruct_abstract("not-a-dict") is None
    assert reconstruct_abstract({"": [0], None: [1], "word": []}) is None
    assert reconstruct_abstract({"word": ["nope", True]}) is None


def test_reconstruct_accepts_a_single_integer_position():
    assert reconstruct_abstract({"Hello": 0, "there": [1]}) == "Hello there"
