SERVER_CONFIG = {
    "command": "bash",
    "args": [
        "-c",
        "docker exec -i mcp-filesystem node"
        " /app/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js"
        " /data 2>/dev/null",
    ],
    "transport": "stdio",
}
