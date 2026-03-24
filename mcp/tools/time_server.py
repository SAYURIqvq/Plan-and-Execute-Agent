"""Time MCP Server — 現在の日時を返す（TZ=Asia/Tokyo）"""

from datetime import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("time")


@mcp.tool()
def get_current_datetime() -> str:
    """Get the current date and time in JST (Japan Standard Time)."""
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S (JST)")


if __name__ == "__main__":
    mcp.run()
