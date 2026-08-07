from integration.one_flow import one_flow_stub


def test_one_flow_stub():
    """
    Test the one_flow_stub function to ensure it executes without errors.
    """
    result = one_flow_stub()
    assert result == "Flow completed successfully."