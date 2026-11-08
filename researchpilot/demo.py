"""Public portfolio demo switch.

When RESEARCHPILOT_PUBLIC_DEMO is true, Gemini requests are refused before
a client is created. The flag is read from the environment and from
Streamlit secrets on each check. If either source is true, demo mode stays
on. There is no in-app control that turns it off.
"""

from __future__ import annotations

import os

PUBLIC_DEMO_MESSAGE = (
    "AI analysis and comparison are disabled in the public portfolio demo."
)
_PUBLIC_DEMO_FLAG = "RESEARCHPILOT_PUBLIC_DEMO"


class PublicDemoError(RuntimeError):
    """A Gemini request was refused because the public demo is on."""


def _value_enables_public_demo(raw: object) -> bool:
    """Return whether one configuration value explicitly turns the demo on."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() == "true"
    return False


def _streamlit_secret(name: str) -> object:
    """Return one Streamlit secret, or None when secrets cannot be read.

    A missing Streamlit install, a missing secrets file, and a missing key
    are all treated as unavailable. Secret values are not logged.
    """
    try:
        import streamlit as st

        secrets = st.secrets
    except Exception:
        return None

    try:
        probe = getattr(secrets, "load_if_toml_exists", None)
        if callable(probe) and not probe():
            return None
        if name not in secrets:
            return None
        return secrets[name]
    except Exception:
        return None


def public_demo_enabled() -> bool:
    """Return whether this process is running as the public demo.

    An explicit true from the environment or from Streamlit secrets enables
    demo mode. A false value from the other source does not turn it off.
    """
    if _value_enables_public_demo(os.getenv(_PUBLIC_DEMO_FLAG)):
        return True
    return _value_enables_public_demo(_streamlit_secret(_PUBLIC_DEMO_FLAG))


def reject_gemini_in_public_demo() -> None:
    """Refuse a Gemini call before any client or network request."""
    if public_demo_enabled():
        raise PublicDemoError(PUBLIC_DEMO_MESSAGE)
