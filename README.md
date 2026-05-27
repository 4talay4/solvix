# Curso IA Telegram

Asistente educativo con **IA local** (Ollama), **RAG** (ChromaDB), tres bots de Telegram y PostgreSQL.

Optimizado para **respuestas rápidas** (caché semántica) y **precisas** (material del curso + citas).

## Infraestructura objetivo

| Servidor | Specs | Rol |
|----------|-------|-----|
| Principal | 8 GB RAM · 2 cores · 80 GB | Todo el stack (recomendado) |
| Auxiliar | 4 GB RAM | Solo Ollama (opcional) |

## Componentes

| Servicio | Función |
|----------|---------|
| `bot-alumnos` | Registro, preguntas, `/bibliografia`, `/test` |
| `bot-admin` | Autorización, stats, **resolver tickets** |
| `bot-soporte` | Mejoras e incidencias |
| `rag-api` | Motor RAG + caché |
| `ollama` | LLM + embeddings locales |
| `chromadb` | Vectores del temario |
| `postgres` | Usuarios, logs, tickets |

## Inicio rápido

1. Copia `.env.example` → `.env` y rellena tokens + Telegram ID.
2. Sigue **[GUIA_DESPLIEGUE_COMPLETA.md](GUIA_DESPLIEGUE_COMPLETA.md)**.

```bash
cp .env.example .env
docker compose up -d --build
bash scripts/pull_models.sh
bash scripts/ingest.sh
```

## Documentación

- **[Guía completa de despliegue](GUIA_DESPLIEGUE_COMPLETA.md)**
- [Manual del administrador](docs/manual-admin.md)

## Estructura

```
curso-ia-telegram/
├── docker-compose.yml
├── shared/              # Modelos BD, utilidades
├── services/
│   ├── bot-alumnos/
│   ├── bot-admin/
│   ├── bot-soporte/
│   └── rag-api/
├── scripts/
├── data/curso/          # Material indexable
└── data/tests/          # Preguntas test JSON
```

## Licencia

Código del proyecto: uso educativo / adapta la licencia que prefieras.
