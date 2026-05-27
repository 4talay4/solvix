#!/usr/bin/env python3
"""
Indexa documentos del curso (PDF, TXT, MD) en ChromaDB.
Uso local o dentro del contenedor rag-api:
  python scripts/ingest_docs.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.config import get_settings

settings = get_settings()
COURSE_DIR = Path(os.getenv("COURSE_DATA_DIR", settings.course_data_dir))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", settings.chunk_size))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", settings.chunk_overlap))


def chunk_text(text: str, documento: str, apartado: str = "", pagina: int | None = None) -> list[dict]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        piece = text[start:end]
        chunks.append(
            {
                "texto": piece,
                "documento": documento,
                "apartado": apartado or f"Fragmento {idx + 1}",
                "pagina": pagina,
            }
        )
        idx += 1
        start = end - CHUNK_OVERLAP
        if start < 0:
            start = 0
        if end >= len(text):
            break
    return chunks


def read_pdf(path: Path) -> list[dict]:
    reader = PdfReader(str(path))
    all_chunks = []
    doc_name = path.stem
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        all_chunks.extend(chunk_text(text, doc_name, apartado=f"Página {i}", pagina=i))
    return all_chunks


def read_text_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    doc_name = path.stem
    # Intentar separar por encabezados markdown
    sections = re.split(r"\n(?=#{1,3}\s)", text)
    if len(sections) <= 1:
        return chunk_text(text, doc_name)
    chunks = []
    for sec in sections:
        lines = sec.strip().split("\n", 1)
        title = lines[0].lstrip("# ").strip() if lines else doc_name
        body = lines[1] if len(lines) > 1 else sec
        chunks.extend(chunk_text(body, doc_name, apartado=title))
    return chunks


def collect_chunks() -> list[dict]:
    if not COURSE_DIR.exists():
        print(f"Directorio no encontrado: {COURSE_DIR}")
        return []
    all_chunks: list[dict] = []
    for path in sorted(COURSE_DIR.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            print(f"Procesando PDF: {path.name}")
            all_chunks.extend(read_pdf(path))
        elif suffix in (".txt", ".md"):
            print(f"Procesando texto: {path.name}")
            all_chunks.extend(read_text_file(path))
    return all_chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    base = os.getenv("OLLAMA_HOST", settings.ollama_host).rstrip("/")
    model = os.getenv("OLLAMA_EMBED_MODEL", settings.ollama_embed_model)
    embeddings = []
    with httpx.Client(timeout=120) as client:
        for text in texts:
            resp = client.post(
                f"{base}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
    return embeddings


def main():
    chunks = collect_chunks()
    if not chunks:
        print("No hay documentos para indexar. Coloca PDF/MD/TXT en data/curso/")
        sys.exit(1)

    host = os.getenv("CHROMA_HOST", settings.chroma_host)
    port = int(os.getenv("CHROMA_PORT", settings.chroma_port))
    collection_name = os.getenv("CHROMA_COLLECTION", settings.chroma_collection)

    client = chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 8
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["texto"] for c in batch]
        embeddings = embed_batch(texts)
        ids = [f"chunk_{i + j}" for j in range(len(batch))]
        metadatas = [
            {
                "documento": c["documento"],
                "apartado": c["apartado"],
                "pagina": c["pagina"] if c.get("pagina") is not None else -1,
            }
            for c in batch
        ]
        collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        print(f"Indexados {min(i + batch_size, len(chunks))}/{len(chunks)}")

    print(f"✅ Ingesta completada: {len(chunks)} fragmentos en '{collection_name}'")


if __name__ == "__main__":
    main()
