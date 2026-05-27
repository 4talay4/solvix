import numpy as np

from shared.config import get_settings
from shared.utils import normalize_text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


async def find_similar_cache(
    question: str,
    embedding: list[float],
    cache_entries: list,
) -> tuple[dict | None, float]:
    settings = get_settings()
    threshold = settings.similarity_cache_threshold
    best_score = 0.0
    best_entry = None
    norm_q = normalize_text(question)

    for entry in cache_entries:
        if entry.embedding_json:
            score = cosine_similarity(embedding, entry.embedding_json)
        else:
            score = 1.0 if entry.question_normalized == norm_q else 0.0
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= threshold:
        return {
            "answer": best_entry.answer_text,
            "sources": best_entry.sources_json or [],
            "cache_id": best_entry.id,
        }, best_score
    return None, best_score
