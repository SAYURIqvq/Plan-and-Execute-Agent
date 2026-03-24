SERVER_CONFIG = {
    "command": "bash",
    "args": [
        "-c",
        "docker exec -i mcp-shell shell-mcp-server /workspace /data"
        " --shell bash /bin/bash 2>/dev/null",
    ],
    "transport": "stdio",
}
