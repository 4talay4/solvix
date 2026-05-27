# Guía de despliegue (resumida)

> **Documento principal:** [GUIA_DESPLIEGUE_COMPLETA.md](../GUIA_DESPLIEGUE_COMPLETA.md)

Incluye: servidor 8 GB, auxiliar 4 GB opcional, `/bibliografia`, resolución de tickets, modelo `qwen2.5:3b`.

## Comandos esenciales

```bash
cp .env.example .env && nano .env
docker compose up -d --build
bash scripts/pull_models.sh
bash scripts/ingest.sh
```
