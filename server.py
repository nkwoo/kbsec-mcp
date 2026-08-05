"""KB증권 OpenAPI MCP 서버 엔트리포인트 (stdio transport)."""
from app import mcp
from tools import (
    domestic_quote,
    domestic_ranking,
    domestic_order,
    domestic_account,
    domestic_order_history,
    domestic_market,
    overseas_quote,
    overseas_account,
    overseas_order,
    overseas_order_history,
    overseas_ranking,
)

__all__ = ["mcp"]

if __name__ == "__main__":
    mcp.run()
