"""Checks that the dashboard CSS keeps the dark palette and card spacing."""

from researchpilot.theme import THEME_CSS


def test_theme_keeps_the_dark_navy_and_purple_palette():
    assert "#0B1020" in THEME_CSS
    assert "#111827" in THEME_CSS
    assert "#172033" in THEME_CSS
    assert "#8B5CF6" in THEME_CSS
    assert "#22D3EE" in THEME_CSS
    assert "#293449" in THEME_CSS


def test_paper_cards_have_inner_padding_and_a_tighter_gap():
    assert 'stVerticalBlockBorderWrapper"]:has(.rp-card)' in THEME_CSS
    assert "padding: 1rem 1.15rem 1.05rem !important" in THEME_CSS
    assert "gap: 0.5rem !important" in THEME_CSS
    assert "margin-bottom: 0" in THEME_CSS
    assert "padding: 0.85rem 0.9rem 0.9rem !important" in THEME_CSS
