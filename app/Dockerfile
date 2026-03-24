FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    langchain \
    langchain-ollama \
    mcp \
    langchain-mcp-adapters \
    pytest \
    pytest-asyncio \
    fastapi \
    "uvicorn[standard]"

COPY app/ .

CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000"]
