#!/bin/bash
set -e
echo "Ejecutando ingesta de documentos..."
docker compose exec -T rag-api python /app/scripts/ingest_docs.py
echo "Ingesta finalizada."
