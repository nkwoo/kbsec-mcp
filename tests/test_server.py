import server


async def test_all_74_tools_registered_with_unique_names():
    tools = await server.mcp.list_tools()
    names = [t.name for t in tools]
    assert len(names) == 74
    assert len(set(names)) == 74


async def test_tool_names_use_expected_category_prefixes():
    expected_prefixes = (
        "quote_kr_",
        "ranking_kr_",
        "order_kr_",
        "account_kr_",
        "orderhist_kr_",
        "market_kr_",
        "quote_os_",
        "account_os_",
        "order_os_",
        "orderhist_os_",
        "ranking_os_",
        "auth_",
    )
    tools = await server.mcp.list_tools()
    for tool in tools:
        assert tool.name.startswith(expected_prefixes), tool.name
