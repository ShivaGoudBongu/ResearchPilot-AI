"""Visual theme for the ResearchPilot Streamlit dashboard."""

import streamlit as st

THEME_CSS = """
<style>
.stApp {
  background-color: #0B1020;
  color: #F8FAFC;
}
section[data-testid="stSidebar"] {
  background-color: #111827;
  border-right: 1px solid #293449;
}
section.main .block-container {
  max-width: 1080px;
  padding-top: 1.75rem;
  padding-bottom: 3rem;
}
.rp-lead {
  color: #94A3B8;
  font-size: 1.125rem;
  line-height: 1.6;
  margin: 0 0 1rem 0;
}
[data-testid="stCaptionContainer"] p {
  color: #94A3B8;
}
[data-testid="stElementContainer"]:has(.rp-card) {
  display: none;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.rp-card) {
  background: #172033;
  border: 1px solid #293449 !important;
  border-radius: 12px;
  padding: 1rem 1.15rem 1.05rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(.rp-card):hover {
  border-color: #8B5CF6 !important;
}
[data-testid="stVerticalBlock"]:has(.rp-card):not(:has([data-testid="stVerticalBlock"] .rp-card)) {
  background: transparent;
  border: none !important;
  gap: 0.5rem !important;
  padding: 0 !important;
}
[data-testid="stVerticalBlock"]:has(.rp-card):not(:has([data-testid="stVerticalBlock"] .rp-card)) [data-testid="stMarkdown"] p {
  margin-top: 0;
  margin-bottom: 0;
}
[data-testid="stVerticalBlock"]:has(.rp-card) [data-testid="stButton"],
[data-testid="stVerticalBlock"]:has(.rp-card) [data-testid="stDownloadButton"],
[data-testid="stVerticalBlock"]:has(.rp-card) [data-testid="stLinkButton"] {
  margin-top: 0.15rem;
  margin-bottom: 0.1rem;
}
[data-testid="stVerticalBlock"]:has(.rp-card) details[data-testid="stExpander"] {
  margin-top: 0.2rem;
  margin-bottom: 0.15rem;
}
details[data-testid="stExpander"] {
  background: #111827;
  border: 1px solid #293449;
  border-radius: 8px;
}
button[data-testid="stBaseButton-secondary"] {
  background: #172033;
  color: #F8FAFC;
  border: 1px solid #293449;
  border-radius: 8px;
}
button[data-testid="stBaseButton-secondary"]:hover {
  border-color: #8B5CF6;
  color: #F8FAFC;
}
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: #6D28D9;
  color: #F8FAFC;
  border: 1px solid #6D28D9;
  border-radius: 8px;
}
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: #7C3AED;
  border-color: #22D3EE;
  color: #F8FAFC;
}
button[data-testid="stBaseButton-secondary"]:disabled,
button[data-testid="stBaseButton-primary"]:disabled,
button[data-testid="stBaseButton-primaryFormSubmit"]:disabled {
  color: #94A3B8 !important;
  background: #111827 !important;
  border-color: #293449 !important;
  opacity: 1;
}
[data-testid="stTextInput"] input {
  background: #0B1020;
  color: #F8FAFC;
  border: 1px solid #293449;
  border-radius: 8px;
}
a, a:visited {
  color: #22D3EE;
}
button:focus-visible,
input:focus-visible,
textarea:focus-visible,
a:focus-visible,
[data-testid="stSidebar"] [role="radiogroup"] label:focus-within {
  outline: 2px solid #22D3EE !important;
  outline-offset: 2px;
}
@media (max-width: 700px) {
  section.main .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
  }
  [data-testid="stVerticalBlockBorderWrapper"]:has(.rp-card) {
    padding: 0.85rem 0.9rem 0.9rem !important;
  }
}
</style>
"""


def inject_theme() -> None:
    """Apply the dashboard colours. Static CSS only; no user content."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)
