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
  padding-top: 0.85rem;
  padding-bottom: 2.5rem;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 5.5rem);
}
.rp-brand {
  color: #F8FAFC;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin: 0.1rem 0 0.05rem;
}
.rp-lead {
  color: #94A3B8;
  font-size: 1.05rem;
  line-height: 1.5;
  margin: 0 0 0.65rem 0;
}
p.rp-meta {
  color: #94A3B8;
  font-size: 0.85rem;
  line-height: 1.4;
  margin: 0.05rem 0 0.2rem;
}
p.rp-preview {
  color: #E2E8F0;
  font-size: 0.95rem;
  line-height: 1.45;
  margin: 0.3rem 0 0.15rem;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
hr.rp-actions {
  border: none;
  border-top: 1px solid #293449;
  margin: 0.35rem 0 0.4rem;
}
[data-testid="stCaptionContainer"] p {
  color: #94A3B8;
}
[data-testid="stElementContainer"]:has(.rp-card),
[data-testid="stElementContainer"]:has(.rp-examples) {
  display: none;
}
[data-testid="stElementContainer"]:has(.rp-side-foot) {
  margin-top: auto;
  height: 0;
  min-height: 0;
  overflow: hidden;
}
[data-testid="stVerticalBlock"]:has(.rp-card):not(:has([data-testid="stVerticalBlock"] .rp-card)) {
  background: #172033;
  border: 1px solid #293449 !important;
  border-radius: 12px;
  padding: 0.55rem 0.8rem 0.65rem;
  gap: 0.2rem;
}
[data-testid="stVerticalBlock"]:has(.rp-missing):not(:has([data-testid="stVerticalBlock"] .rp-missing)) {
  border-left: 3px solid #94A3B8 !important;
}
[data-testid="stVerticalBlock"]:has(.rp-card):not(:has([data-testid="stVerticalBlock"] .rp-card)):hover {
  border-color: #8B5CF6 !important;
}
[data-testid="stForm"] {
  background: #172033;
  border: 1px solid #293449;
  border-radius: 12px;
  padding: 0.15rem 0.75rem 0.55rem;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] {
  margin-top: 0.85rem;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
  padding-top: 0.28rem;
  padding-bottom: 0.28rem;
}
[data-testid="stVerticalBlock"]:has(.rp-examples):not(:has([data-testid="stVerticalBlock"] .rp-examples)) button {
  min-height: 2.05rem;
  padding-top: 0.2rem;
  padding-bottom: 0.2rem;
  white-space: normal;
}
details[data-testid="stExpander"] {
  background: transparent;
  border: none;
  border-top: 1px solid #293449;
  border-radius: 0;
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
  font-weight: 600;
}
button[data-testid="stBaseButton-primaryFormSubmit"] {
  min-height: 2.75rem;
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
    padding-top: 0.5rem;
    padding-left: 0.75rem;
    padding-right: 0.75rem;
  }
  [data-testid="stVerticalBlock"]:has(.rp-card):not(:has([data-testid="stVerticalBlock"] .rp-card)) {
    padding: 0.5rem 0.65rem 0.55rem;
  }
}
</style>
"""


def inject_theme() -> None:
    """Apply the dashboard colours. Static CSS only; no user content."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)
