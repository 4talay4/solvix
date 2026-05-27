from shared.utils import normalize_text

from rag.cache import find_similar_cache
from rag.chroma_store import query_documents
from rag.ollama_client import OllamaClient

SYSTEM_PROMPT = """Eres un asistente académico para alumnos de un curso.
Responde SOLO con la información del CONTEXTO proporcionado.
Si el contexto no contiene la respuesta, di claramente que no encuentras esa información en el material del curso.
Responde en español, de forma clara y estructurada.
Al final, indica de qué documento y apartado proviene la información."""


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        header = f"[Fragmento {i}] Documento: {c.get('documento','')} | Apartado: {c.get('apartado','')}"
        if c.get("pagina"):
            header += f" | Página: {c['pagina']}"
        parts.append(f"{header}\n{c.get('texto','')}")
    return "\n\n".join(parts)


def extract_sources(chunks: list[dict]) -> list[dict]:
    seen = set()
    sources = []
    for c in chunks:
        key = (c.get("documento"), c.get("apartado"), c.get("pagina"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "documento": c.get("documento", ""),
                "apartado": c.get("apartado", ""),
                "pagina": c.get("pagina"),
            }
        )
    return sources


async def answer_question(question: str, cache_entries: list) -> dict:
    ollama = OllamaClient()
    embedding = await ollama.embed(question)

    cached, score = await find_similar_cache(question, embedding, cache_entries)
    if cached:
        return {
            "answer": cached["answer"],
            "sources": cached["sources"],
            "from_cache": True,
            "cache_id": cached.get("cache_id"),
            "similarity": score,
            "embedding": embedding,
            "normalized": normalize_text(question),
        }

    chunks = query_documents(embedding, n_results=4)
    if not chunks:
        answer = (
            "No hay material del curso indexado todavía. "
            "El administrador debe ejecutar la ingesta de documentos."
        )
        return {
            "answer": answer,
            "sources": [],
            "from_cache": False,
            "embedding": embedding,
            "normalized": normalize_text(question),
        }

    context = build_context(chunks)
    user_prompt = f"""CONTEXTO DEL CURSO:
{context}

PREGUNTA DEL ALUMNO:
{question}

Responde usando únicamente el contexto."""

    answer = await ollama.generate(user_prompt, system=SYSTEM_PROMPT)
    sources = extract_sources(chunks)

    return {
        "answer": answer,
        "sources": sources,
        "from_cache": False,
        "embedding": embedding,
        "normalized": normalize_text(question),
    }
