FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared /app/shared
COPY services/rag-api/requirements.txt /app/services/rag-api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/rag-api/requirements.txt

COPY services/rag-api /app/services/rag-api
COPY scripts/ingest_docs.py /app/scripts/ingest_docs.py
COPY data /app/data

ENV PYTHONPATH=/app

WORKDIR /app/services/rag-api
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
