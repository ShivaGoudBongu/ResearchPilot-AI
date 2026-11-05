"""ResearchPilot AI — Phase 1 paper discovery."""

__version__ = "0.1.0"

from researchpilot.models import Paper
from researchpilot.openalex import OpenAlexClient, OpenAlexError

__all__ = ["OpenAlexClient", "OpenAlexError", "Paper", "__version__"]
