"""ResearchPilot AI — paper discovery and abstract analysis."""

__version__ = "0.2.0"

from researchpilot.analyzer import AnalysisError, analyze_paper
from researchpilot.models import Paper
from researchpilot.openalex import OpenAlexClient, OpenAlexError

__all__ = [
    "AnalysisError",
    "OpenAlexClient",
    "OpenAlexError",
    "Paper",
    "analyze_paper",
    "__version__",
]
