"""SQLite MCP Server — /data/agent.db への SQL 操作"""

import sqlite3

from mcp.server.fastmcp import FastMCP

DB_PATH = "/data/agent.db"

mcp = FastMCP("sqlite")


@mcp.tool()
def list_tables() -> str:
    """List all tables in the SQLite database (/data/agent.db)."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return str([r[0] for r in rows]) if rows else "No tables found."


@mcp.tool()
def query(sql: str) -> str:
    """Execute a SQL statement. SELECT returns rows; INSERT/UPDATE/DELETE returns affected count."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(sql)
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                return str(rows) if rows else "No rows returned."
            conn.commit()
            return f"OK: {cur.rowcount} rows affected."
    except sqlite3.Error as e:
        return f"SQL error: {e}"


if __name__ == "__main__":
    mcp.run()
