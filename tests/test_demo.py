"""Public demo mode refuses Gemini before a client is created."""

import pytest

from researchpilot.analyzer import analyze_paper, generate_text
from researchpilot.comparison import SelectionError, compare_papers
from researchpilot.demo import PUBLIC_DEMO_MESSAGE, PublicDemoError, public_demo_enabled
from researchpilot.models import Paper
from researchpilot.usage import ANALYSIS_REQUEST_LIMIT, COMPARISON_REQUEST_LIMIT


def _paper(index: int) -> Paper:
    return Paper(
        title=f"Paper {index}",
        authors=["Ada Lovelace"],
        publication_year=2020,
        doi=f"https://doi.org/10.1000/demo{index}",
        abstract=f"Abstract {index} is long enough to analyse.",
        source_url=f"https://example/{index}",
        openalex_id=f"https://openalex.org/W{index}",
    )


def _forbid_client(*_args, **_kwargs):
    raise AssertionError("Gemini client should not be created")


class _Secrets:
    """Small stand-in for st.secrets. It stores no real credentials."""

    def __init__(self, values, available=True, error=None):
        self._values = values
        self._available = available
        self._error = error

    def load_if_toml_exists(self):
        if self._error is not None:
            raise self._error
        return self._available

    def __contains__(self, key):
        return key in self._values

    def __getitem__(self, key):
        return self._values[key]


def test_public_demo_is_off_unless_the_value_is_true(monkeypatch):
    monkeypatch.delenv("RESEARCHPILOT_PUBLIC_DEMO", raising=False)
    assert public_demo_enabled() is False
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "false")
    assert public_demo_enabled() is False
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "")
    assert public_demo_enabled() is False
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    assert public_demo_enabled() is True


def test_public_demo_blocks_analysis_before_a_client(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "demo-must-not-leak")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", _forbid_client)

    with pytest.raises(PublicDemoError, match=PUBLIC_DEMO_MESSAGE) as caught:
        analyze_paper("Graph models", "We predict binding from molecular graphs.")

    assert "demo-must-not-leak" not in str(caught.value)


def test_public_demo_blocks_comparison_before_a_client(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "demo-must-not-leak")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", _forbid_client)

    with pytest.raises(PublicDemoError, match=PUBLIC_DEMO_MESSAGE) as caught:
        compare_papers([_paper(1), _paper(2), _paper(3)])

    assert "demo-must-not-leak" not in str(caught.value)


def test_public_demo_blocks_generate_text_before_a_client(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "demo-must-not-leak")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", _forbid_client)

    with pytest.raises(PublicDemoError, match=PUBLIC_DEMO_MESSAGE):
        generate_text("Do not send this prompt.")


def test_invalid_comparison_is_still_rejected_before_the_demo_guard(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", _forbid_client)

    with pytest.raises(SelectionError, match="at least 3"):
        compare_papers([_paper(1), _paper(2)])


def test_environment_variable_true_enables_public_demo(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setattr("streamlit.secrets", _Secrets({}, available=False))

    assert public_demo_enabled() is True


def test_streamlit_secret_true_enables_public_demo(monkeypatch):
    monkeypatch.delenv("RESEARCHPILOT_PUBLIC_DEMO", raising=False)
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": True}),
    )
    assert public_demo_enabled() is True

    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": "true"}),
    )
    assert public_demo_enabled() is True


def test_public_demo_is_off_when_both_sources_are_missing(monkeypatch):
    monkeypatch.delenv("RESEARCHPILOT_PUBLIC_DEMO", raising=False)
    monkeypatch.setattr("streamlit.secrets", _Secrets({}, available=False))

    assert public_demo_enabled() is False


def test_either_true_source_keeps_public_demo_enabled(monkeypatch):
    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "false")
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": True}),
    )
    assert public_demo_enabled() is True

    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": False}),
    )
    assert public_demo_enabled() is True

    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "false")
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": False}),
    )
    assert public_demo_enabled() is False


def test_unavailable_streamlit_secrets_are_ignored(monkeypatch):
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({}, error=RuntimeError("secrets unavailable")),
    )
    monkeypatch.delenv("RESEARCHPILOT_PUBLIC_DEMO", raising=False)
    assert public_demo_enabled() is False

    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "false")
    assert public_demo_enabled() is False

    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "true")
    assert public_demo_enabled() is True


def test_streamlit_secret_blocks_gemini_before_a_client(monkeypatch):
    monkeypatch.delenv("RESEARCHPILOT_PUBLIC_DEMO", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "demo-must-not-leak")
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": True}),
    )
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", _forbid_client)

    with pytest.raises(PublicDemoError, match=PUBLIC_DEMO_MESSAGE) as caught:
        analyze_paper("Graph models", "We predict binding from molecular graphs.")

    assert "demo-must-not-leak" not in str(caught.value)
    with pytest.raises(PublicDemoError, match=PUBLIC_DEMO_MESSAGE):
        generate_text("Do not send this prompt.")


def test_local_mode_still_calls_gemini_and_keeps_session_limits(monkeypatch):
    captured = {}

    class FakeModels:
        def generate_content(self, model, contents):
            captured["model"] = model
            captured["contents"] = contents
            return type("Response", (), {"text": "Saved local analysis."})()

    class FakeClient:
        def __init__(self, api_key):
            captured["key_used"] = api_key == "local-test-key"
            self.models = FakeModels()

    monkeypatch.setenv("RESEARCHPILOT_PUBLIC_DEMO", "false")
    monkeypatch.setattr(
        "streamlit.secrets",
        _Secrets({"RESEARCHPILOT_PUBLIC_DEMO": False}),
    )
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-key")
    monkeypatch.setattr("researchpilot.analyzer.genai.Client", FakeClient)

    assert public_demo_enabled() is False
    assert analyze_paper("Title", "An abstract is present.") == "Saved local analysis."
    assert captured["key_used"] is True
    assert captured["model"] == "gemini-3.5-flash-lite"
    assert "local-test-key" not in captured["contents"]
    assert ANALYSIS_REQUEST_LIMIT == 5
    assert COMPARISON_REQUEST_LIMIT == 2
