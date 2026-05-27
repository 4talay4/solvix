#!/bin/bash
set -e
echo "Ejecutando ingesta de documentos..."
docker compose exec rag-api python /app/scripts/ingest_docs.py
echo "Ingesta finalizada."
