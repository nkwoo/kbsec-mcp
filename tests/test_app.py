from app import mcp


def test_mcp_instance_has_expected_name():
    assert mcp.name == "kbsec"
