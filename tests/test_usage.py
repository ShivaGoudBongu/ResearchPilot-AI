"""Session limits count outgoing Gemini requests only."""

from researchpilot.usage import (
    ANALYSIS_REQUEST_LIMIT,
    COMPARISON_REQUEST_LIMIT,
    analysis_request_is_outgoing,
    comparison_request_is_outgoing,
    record_outgoing_request,
    remaining_requests,
    request_allowed,
)


def test_analysis_and_comparison_limits_are_separate():
    assert ANALYSIS_REQUEST_LIMIT == 5
    assert COMPARISON_REQUEST_LIMIT == 2
    used = 0
    for _ in range(ANALYSIS_REQUEST_LIMIT):
        assert request_allowed(used, ANALYSIS_REQUEST_LIMIT)
        used = record_outgoing_request(used)
    assert used == 5
    assert remaining_requests(used, ANALYSIS_REQUEST_LIMIT) == 0
    assert not request_allowed(used, ANALYSIS_REQUEST_LIMIT)
    assert request_allowed(used, COMPARISON_REQUEST_LIMIT) is False
    assert remaining_requests(0, COMPARISON_REQUEST_LIMIT) == 2
    assert record_outgoing_request(True) == 1


def test_cached_invalid_and_unconfigured_requests_are_not_outgoing():
    assert analysis_request_is_outgoing({"status": "ok", "text": "saved"}, True, True) is False
    assert analysis_request_is_outgoing(None, False, True) is False
    assert analysis_request_is_outgoing(None, True, False) is False
    assert analysis_request_is_outgoing(None, True, True) is True
    assert analysis_request_is_outgoing({"status": "error"}, True, True) is True

    assert comparison_request_is_outgoing(False, None, True) is False
    assert comparison_request_is_outgoing(True, "ok", True) is False
    assert comparison_request_is_outgoing(True, None, False) is False
    assert comparison_request_is_outgoing(True, None, True) is True
    assert comparison_request_is_outgoing(True, "error", True) is True
