SERVER_CONFIG = {
    "command": "bash",
    "args": [
        "-c",
        "docker exec -i mcp-websearch python /app/server.py 2>/dev/null",
    ],
    "transport": "stdio",
}
