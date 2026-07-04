FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app/ .

CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000"]
