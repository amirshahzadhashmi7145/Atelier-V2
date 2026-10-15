import pytest


@pytest.mark.skip(reason="Gateway uses Chat Completions today; Responses/reasoning pairing uses the same assert when that path is added.")
def test_responses_api_recorded_fixture_reserved():
    """Placeholder for a recorded Responses API fixture (reasoning items + tool outputs)."""
    assert True
