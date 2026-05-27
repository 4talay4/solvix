import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# PYTHONPATH=/app
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.db import AsyncSessionLocal
from shared.repository import bump_cache_hit, get_cache_candidates, upsert_cache_entry
from rag.pipeline import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Curso RAG API", version="1.0.0")


class AskRequest(BaseModel):
    question: str
    user_id: int | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    from_cache: bool
    cache_id: int | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    question = req.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=400, detail="Pregunta demasiado corta")

    async with AsyncSessionLocal() as session:
        cache_entries = await get_cache_candidates(session)
        result = await answer_question(question, cache_entries)

        cache_id = result.get("cache_id")
        if result.get("from_cache") and cache_id:
            await bump_cache_hit(session, cache_id)
        elif not result.get("from_cache"):
            await upsert_cache_entry(
                session,
                question=question,
                normalized=result["normalized"],
                answer=result["answer"],
                sources=result["sources"],
                embedding=result.get("embedding"),
            )
        await session.commit()

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        from_cache=result.get("from_cache", False),
        cache_id=result.get("cache_id"),
    )


@app.post("/embed")
async def embed_text(body: dict):
    from rag.ollama_client import OllamaClient

    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text requerido")
    client = OllamaClient()
    return {"embedding": await client.embed(text)}
