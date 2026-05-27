#!/bin/bash
# Descarga modelos en Ollama (ejecutar tras levantar docker compose)
set -e
MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
EMBED="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"

echo "Descargando modelo de chat: $MODEL"
docker compose exec ollama ollama pull "$MODEL"

echo "Descargando modelo de embeddings: $EMBED"
docker compose exec ollama ollama pull "$EMBED"

echo "Modelos listos."
