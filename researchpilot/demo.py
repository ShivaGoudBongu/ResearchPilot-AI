"""Public portfolio demo switch.

When RESEARCHPILOT_PUBLIC_DEMO is true, Gemini requests are refused before
a client is created. The value is read from the environment on each check.
There is no in-app control that turns it off.
"""

from __future__ import annotations

import os

PUBLIC_DEMO_MESSAGE = (
    "AI analysis and comparison are disabled in the public portfolio demo."
)


class PublicDemoError(RuntimeError):
    """A Gemini request was refused because the public demo is on."""


def public_demo_enabled() -> bool:
    """Return whether this process is running as the public demo."""
    raw = os.getenv("RESEARCHPILOT_PUBLIC_DEMO")
    if not isinstance(raw, str):
        return False
    return raw.strip().lower() == "true"


def reject_gemini_in_public_demo() -> None:
    """Refuse a Gemini call before any client or network request."""
    if public_demo_enabled():
        raise PublicDemoError(PUBLIC_DEMO_MESSAGE)
