import json
import re
from pathlib import Path

from pypdf import PdfReader

from shared.config import get_settings

SUPPORTED = {".pdf", ".md", ".txt"}
MANIFEST_NAME = "bibliografia.json"


def _course_dir() -> Path:
    return Path(get_settings().course_data_dir)


def _load_manifest() -> dict:
    manifest_path = _course_dir() / MANIFEST_NAME
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"documentos": []}


def _md_outline(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    outline = []
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)", line.strip())
        if m:
            level = len(m.group(1))
            indent = "  " * (level - 1)
            outline.append(f"{indent}• {m.group(2).strip()}")
    return outline[:25]


def _pdf_info(path: Path) -> tuple[int, list[str]]:
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        outline = []
        if reader.outline:
            for item in reader.outline[:15]:
                if isinstance(item, list):
                    continue
                title = getattr(item, "title", None) or str(item)
                outline.append(f"• {title}")
        return pages, outline
    except Exception:
        return 0, []


def list_course_documents() -> list[dict]:
    course_dir = _course_dir()
    if not course_dir.exists():
        return []

    manifest = _load_manifest()
    manifest_by_file = {d.get("archivo", ""): d for d in manifest.get("documentos", [])}
    docs: list[dict] = []

    for path in sorted(course_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == MANIFEST_NAME or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED:
            continue

        meta = manifest_by_file.get(path.name, {})
        rel = path.relative_to(course_dir).as_posix()
        docs.append(
            {
                "archivo": path.name,
                "ruta_relativa": rel,
                "titulo": meta.get("titulo") or path.stem.replace("-", " ").replace("_", " ").title(),
                "descripcion": meta.get("descripcion", ""),
                "tipo": suffix.lstrip(".").upper(),
                "bytes": path.stat().st_size,
                "path": path,
            }
        )

    docs.sort(key=lambda d: d["titulo"].lower())
    return docs


def get_document_detail(index: int) -> dict | None:
    docs = list_course_documents()
    if index < 0 or index >= len(docs):
        return None
    doc = docs[index].copy()
    path: Path = doc["path"]
    suffix = path.suffix.lower()

    doc["tamano_legible"] = _human_size(doc["bytes"])
    doc["indice"] = []

    if suffix == ".md":
        doc["indice"] = _md_outline(path)
    elif suffix == ".pdf":
        pages, outline = _pdf_info(path)
        doc["paginas"] = pages
        doc["indice"] = outline or [f"Documento PDF ({pages} páginas)"]
    elif suffix == ".txt":
        preview = path.read_text(encoding="utf-8", errors="ignore")[:500]
        doc["indice"] = [preview[:200] + "…"] if len(preview) > 200 else [preview]

    doc["enviable"] = doc["bytes"] <= 20 * 1024 * 1024
    return doc


def _human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"
