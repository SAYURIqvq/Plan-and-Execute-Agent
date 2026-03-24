"""Memory MCP Server — セッションをまたいだ key-value メモリ（/data/memory.json）"""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

MEMORY_FILE = Path("/data/memory.json")

mcp = FastMCP("memory")


def _load() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@mcp.tool()
def remember(key: str, value: str) -> str:
    """Save or update a memory entry."""
    data = _load()
    data[key] = value
    _save(data)
    return f"Remembered: {key} = {value}"


@mcp.tool()
def recall(key: str) -> str:
    """Retrieve a memory entry by key."""
    return _load().get(key, f"No memory found for key: '{key}'")


@mcp.tool()
def list_memories() -> str:
    """List all stored memory entries."""
    data = _load()
    if not data:
        return "No memories stored."
    return "\n".join(f"- {k}: {v}" for k, v in data.items())


@mcp.tool()
def forget(key: str) -> str:
    """Delete a memory entry by key."""
    data = _load()
    if key not in data:
        return f"Key not found: '{key}'"
    del data[key]
    _save(data)
    return f"Forgotten: {key}"


if __name__ == "__main__":
    mcp.run()
