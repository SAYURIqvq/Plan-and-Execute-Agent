"""
Web Search MCP Server

DuckDuckGo を使ったウェブ検索 MCP サーバー（APIキー不要）

ツール:
  web_search  - DuckDuckGo でキーワード検索し、タイトル・URL・概要を返す
  fetch_page  - 指定 URL のページ本文テキストを取得する
"""

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("websearch")


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns titles, URLs and snippets."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   URL: {r['href']}\n   {r['body']}")
    return "\n\n".join(lines)


@mcp.tool()
def fetch_page(url: str) -> str:
    """Fetch and extract text content from a web page (max 8000 chars)."""
    try:
        with httpx.Client(follow_redirects=True, timeout=15) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"Error: {e.response.status_code} {e.response.reason_phrase} for {url}"
    except httpx.RequestError as e:
        return f"Error: failed to fetch {url}: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)[:8000]


if __name__ == "__main__":
    mcp.run()
