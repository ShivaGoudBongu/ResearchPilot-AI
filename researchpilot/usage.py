"""Session limits for outgoing Gemini requests.

The counters are for one Streamlit browser session. They are not an account
quota and they do not measure provider billing.
"""

ANALYSIS_REQUEST_LIMIT = 5
COMPARISON_REQUEST_LIMIT = 2


def normalize_used(used: object) -> int:
    """Return a non-negative request count."""
    if isinstance(used, bool) or not isinstance(used, int) or used < 0:
        return 0
    return used


def remaining_requests(used: object, limit: int) -> int:
    """Return how many requests of this kind are still allowed."""
    return max(0, limit - normalize_used(used))


def request_allowed(used: object, limit: int) -> bool:
    """Return whether another outgoing request is still allowed."""
    return remaining_requests(used, limit) > 0


def record_outgoing_request(used: object) -> int:
    """Count one request that is about to be sent to Gemini."""
    return normalize_used(used) + 1


def analysis_request_is_outgoing(
    stored: dict | None,
    has_abstract: bool,
    api_key_configured: bool,
) -> bool:
    """Return whether an analysis click would send a Gemini request.

    A saved success, a paper with no abstract, and a missing API key stay
    local. A missing or failed analysis is an outgoing attempt when the key
    is configured.
    """
    if not has_abstract or not api_key_configured:
        return False
    if isinstance(stored, dict) and stored.get("status") == "ok":
        return False
    return True


def comparison_request_is_outgoing(
    selection_ok: bool,
    cached_status: str | None,
    api_key_configured: bool,
) -> bool:
    """Return whether a comparison click would send a Gemini request.

    Invalid selections and successful cached comparisons do not. A failed
    comparison can be sent again, so that retry counts.
    """
    if not selection_ok or not api_key_configured:
        return False
    return cached_status != "ok"
