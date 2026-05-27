import chromadb
from chromadb.config import Settings as ChromaSettings

from shared.config import get_settings


def get_collection():
    settings = get_settings()
    client = chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )


def query_documents(embedding: list[float], n_results: int = 4) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    chunks = []
    for doc, meta, dist in zip(docs, metas, distances):
        pagina = meta.get("pagina")
        if pagina is not None and int(pagina) < 0:
            pagina = None
        chunks.append(
            {
                "texto": doc,
                "documento": meta.get("documento", ""),
                "apartado": meta.get("apartado", ""),
                "pagina": pagina,
                "score": 1 - dist if dist is not None else None,
            }
        )
    return chunks
