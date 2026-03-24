SERVER_CONFIG = {
    "command": "bash",
    "args": [
        "-c",
        "docker exec -i mcp-tools python /app/time_server.py 2>/dev/null",
    ],
    "transport": "stdio",
}
