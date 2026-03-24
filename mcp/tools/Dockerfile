FROM python:3.11-slim

RUN pip install --no-cache-dir mcp

WORKDIR /app

COPY mcp/tools/ .

CMD ["tail", "-f", "/dev/null"]
