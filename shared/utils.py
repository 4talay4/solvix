import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s¿?¡!.,;:]", "", text)
    return text


def user_display_name(user) -> str:
    if user.nombre and user.apellidos:
        return f"{user.nombre} {user.apellidos}"
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or f"ID {user.telegram_id}"


def format_sources(sources: list[dict]) -> str:
    if not sources:
        return ""
    lines = ["\n\n📚 **Fuentes:**"]
    for i, src in enumerate(sources, 1):
        doc = src.get("documento", "Desconocido")
        section = src.get("apartado", "")
        page = src.get("pagina")
        part = f"{i}. *{doc}*"
        if section:
            part += f" — {section}"
        if page:
            part += f" (pág. {page})"
        lines.append(part)
    return "\n".join(lines)
