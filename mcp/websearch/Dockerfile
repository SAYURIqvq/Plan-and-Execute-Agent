FROM python:3.11-slim

RUN pip install --no-cache-dir \
    mcp \
    ddgs \
    httpx \
    beautifulsoup4

WORKDIR /app

COPY mcp/websearch/server.py .

CMD ["tail", "-f", "/dev/null"]
