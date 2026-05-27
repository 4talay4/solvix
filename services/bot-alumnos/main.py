import json
import logging
import sys
from enum import Enum
from pathlib import Path

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config import get_settings
from shared.db import AsyncSessionLocal
from shared.models import UserStatus
from shared.notify import notify_admins
from shared.repository import (
    complete_registration,
    create_or_touch_user,
    get_user_by_telegram_id,
    log_activity,
    save_question_history,
)
from shared.bibliografia import get_document_detail, list_course_documents
from shared.utils import format_sources, user_display_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

NOMBRE, APELLIDOS = range(2)


class RegState(str, Enum):
    nombre = "nombre"
    apellidos = "apellidos"


HELP_TEXT = """🎓 *Bot del curso*

Comandos:
/start — Registrarte o reiniciar sesión
/help — Esta ayuda
/bibliografia — Consultar documentos del temario
/test — Ver preguntas tipo test resueltas

Cuando estés autorizado, escribe cualquier pregunta del temario en lenguaje natural."""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_tg = update.effective_user
    if not user_tg or not update.message:
        return ConversationHandler.END

    async with AsyncSessionLocal() as session:
        user = await create_or_touch_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
            last_name=user_tg.last_name,
        )
        await log_activity(session, "bot_start", telegram_id=user_tg.id, user_id=user.id)
        await session.commit()

        if user.status == UserStatus.autorizado:
            await update.message.reply_text(
                f"¡Hola, {user_display_name(user)}! 👋\n\n"
                "Ya estás autorizado. Escribe tu pregunta del temario cuando quieras.\n\n"
                "Usa /bibliografia para el temario, /test para exámenes o /help para más info.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        if user.status == UserStatus.pendiente:
            await update.message.reply_text(
                "⏳ Tu registro está *pendiente de autorización*.\n"
                "El administrador revisará tu solicitud pronto.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

        if user.status == UserStatus.rechazado:
            await update.message.reply_text(
                "❌ Tu solicitud de acceso fue rechazada. Contacta con el administrador del curso."
            )
            return ConversationHandler.END

    await update.message.reply_text(
        "👋 Bienvenido al asistente del curso.\n\n"
        "Para registrarte, escribe tu *nombre*:",
        parse_mode="Markdown",
    )
    return NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NOMBRE
    nombre = update.message.text.strip()
    if len(nombre) < 2:
        await update.message.reply_text("El nombre debe tener al menos 2 caracteres. Inténtalo de nuevo:")
        return NOMBRE
    context.user_data["nombre"] = nombre
    await update.message.reply_text("Ahora escribe tus *apellidos*:", parse_mode="Markdown")
    return APELLIDOS


async def recibir_apellidos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_tg = update.effective_user
    if not user_tg or not update.message or not update.message.text:
        return APELLIDOS

    apellidos = update.message.text.strip()
    if len(apellidos) < 2:
        await update.message.reply_text("Los apellidos deben tener al menos 2 caracteres:")
        return APELLIDOS

    nombre = context.user_data.get("nombre", "")

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, user_tg.id)
        if not user:
            await update.message.reply_text("Error de registro. Usa /start de nuevo.")
            return ConversationHandler.END

        await complete_registration(session, user, nombre, apellidos)
        await log_activity(
            session,
            "registro_completado",
            user_id=user.id,
            telegram_id=user_tg.id,
            detail=f"{nombre} {apellidos}",
        )
        await session.commit()
        user_id = user.id

    await update.message.reply_text(
        "✅ Registro completado.\n\n"
        "Tu cuenta está *pendiente de autorización*. No podrás usar el bot hasta que el administrador te apruebe.",
        parse_mode="Markdown",
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aceptar", callback_data=f"auth:accept:{user_tg.id}"),
                InlineKeyboardButton("❌ Rechazar", callback_data=f"auth:reject:{user_tg.id}"),
            ]
        ]
    )
    admin_msg = (
        f"🆕 *Nuevo registro*\n\n"
        f"ID: `{user_tg.id}`\n"
        f"Usuario: @{user_tg.username or 'sin_username'}\n"
        f"Nombre: *{nombre} {apellidos}*\n"
        f"User DB id: {user_id}"
    )
    await notify_admins(admin_msg, reply_markup=keyboard.to_dict())

    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def bibliografia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    allowed, user = await _user_authorized(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(_status_message(user))
        return

    docs = list_course_documents()
    if not docs:
        await update.message.reply_text(
            "📚 No hay documentos en la biblioteca todavía.\n"
            "El administrador debe añadir material en el temario."
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"📄 {d['titulo'][:55]}", callback_data=f"bib:{i}")]
        for i, d in enumerate(docs[:25])
    ]
    await update.message.reply_text(
        "📚 *Bibliografía del curso*\n\n"
        "Selecciona un documento para ver su descripción e índice.\n"
        f"_{len(docs)} documento(s) disponible(s)._",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

    async with AsyncSessionLocal() as session:
        await log_activity(
            session,
            "bibliografia_listado",
            user_id=user.id if user else None,
            telegram_id=update.effective_user.id,
        )
        await session.commit()


async def bibliografia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    allowed, _user = await _user_authorized(update.effective_user.id)
    if not allowed:
        await query.answer("No autorizado", show_alert=True)
        return

    await query.answer()
    idx = int(query.data.split(":")[1])
    doc = get_document_detail(idx)
    if not doc:
        await query.edit_message_text("Documento no encontrado.")
        return

    lines = [
        f"📄 *{doc['titulo']}*",
        f"Archivo: `{doc['archivo']}`",
        f"Tipo: {doc['tipo']} · Tamaño: {doc['tamano_legible']}",
    ]
    if doc.get("paginas"):
        lines.append(f"Páginas: {doc['paginas']}")
    if doc.get("descripcion"):
        lines.append(f"\n_{doc['descripcion']}_")
    if doc.get("indice"):
        lines.append("\n*Índice / contenido:*")
        lines.extend(doc["indice"][:20])

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n…"

    keyboard = []
    if doc.get("enviable"):
        keyboard.append(
            [InlineKeyboardButton("📥 Recibir archivo en Telegram", callback_data=f"bibfile:{idx}")]
        )
    keyboard.append([InlineKeyboardButton("◀️ Volver al listado", callback_data="bib:list")])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


async def bibliografia_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    # Reutilizar listado editando el mensaje
    docs = list_course_documents()
    keyboard = [
        [InlineKeyboardButton(f"📄 {d['titulo'][:55]}", callback_data=f"bib:{i}")]
        for i, d in enumerate(docs[:25])
    ]
    await query.edit_message_text(
        "📚 *Bibliografía del curso*\n\nSelecciona un documento:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def bibliografia_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    allowed, user = await _user_authorized(update.effective_user.id)
    if not allowed:
        await query.answer("No autorizado", show_alert=True)
        return

    idx = int(query.data.split(":")[1])
    doc = get_document_detail(idx)
    if not doc or not doc.get("enviable"):
        await query.answer("Archivo no disponible", show_alert=True)
        return

    path: Path = doc["path"]
    await query.answer("Enviando archivo…")
    try:
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=doc["archivo"],
                caption=f"📚 {doc['titulo']}",
            )
        async with AsyncSessionLocal() as session:
            await log_activity(
                session,
                "bibliografia_descarga",
                user_id=user.id if user else None,
                telegram_id=update.effective_user.id,
                detail=doc["archivo"],
            )
            await session.commit()
    except Exception as e:
        logger.exception("Error enviando documento: %s", e)
        await context.bot.send_message(
            update.effective_user.id,
            "No pude enviar el archivo. Prueba más tarde o contacta soporte.",
        )


async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    allowed, user = await _user_authorized(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(_status_message(user))
        return

    tests_path = Path(settings.tests_data_file)
    if not tests_path.exists():
        await update.message.reply_text("No hay archivo de tests configurado todavía.")
        return

    data = json.loads(tests_path.read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    if not tests:
        await update.message.reply_text("El archivo de tests está vacío.")
        return

    keyboard = [
        [InlineKeyboardButton(t["titulo"][:60], callback_data=f"test:{i}")]
        for i, t in enumerate(tests[:20])
    ]
    await update.message.reply_text(
        "📝 *Preguntas tipo test resueltas*\nElige un bloque:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    idx = int(query.data.split(":")[1])
    tests_path = Path(settings.tests_data_file)
    tests = json.loads(tests_path.read_text(encoding="utf-8")).get("tests", [])
    if idx >= len(tests):
        await query.edit_message_text("Test no encontrado.")
        return

    block = tests[idx]
    lines = [f"📘 *{block['titulo']}*\n"]
    for q in block.get("preguntas", [])[:10]:
        lines.append(f"\n*{q['id']}.* {q['enunciado']}")
        for opt_key, opt_val in q.get("opciones", {}).items():
            mark = "✅" if opt_key == q.get("correcta") else "○"
            lines.append(f"  {mark} {opt_key}) {opt_val}")
        lines.append(f"\n💡 *Solución:* {q.get('explicacion', '')}\n")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n…(recortado)"
    await query.edit_message_text(text, parse_mode="Markdown")


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return

    telegram_id = update.effective_user.id
    question = update.message.text.strip()

    allowed, user = await _user_authorized(telegram_id)
    if not allowed:
        await update.message.reply_text(_status_message(user))
        return

    await update.message.reply_text("🔍 Analizando tu pregunta, un momento…")

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{settings.rag_api_url.rstrip('/')}/ask",
                json={"question": question, "user_id": user.id if user else None},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.exception("Error RAG: %s", e)
        await update.message.reply_text(
            "⚠️ No pude procesar la pregunta ahora. Inténtalo más tarde o contacta soporte."
        )
        return

    answer = data["answer"]
    sources = data.get("sources", [])
    from_cache = data.get("from_cache", False)
    full = answer + format_sources(sources)
    if from_cache:
        full = "⚡ *Respuesta rápida* (pregunta similar ya respondida)\n\n" + full

    async with AsyncSessionLocal() as session:
        await save_question_history(
            session,
            user_id=user.id if user else None,
            question=question,
            answer=answer,
            from_cache=from_cache,
            sources=sources,
        )
        await log_activity(
            session,
            "pregunta",
            user_id=user.id if user else None,
            telegram_id=telegram_id,
            detail=question[:200],
            metadata={"from_cache": from_cache},
        )
        await session.commit()

    await update.message.reply_text(full, parse_mode="Markdown")
    await update.message.reply_text("¿Tienes otra pregunta del temario? Escríbela cuando quieras. 🙂")


async def _user_authorized(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False, None
    return user.status == UserStatus.autorizado, user


def _status_message(user) -> str:
    if not user:
        return "Usa /start para registrarte primero."
    if user.status == UserStatus.registrando:
        return "Completa el registro con /start"
    if user.status == UserStatus.pendiente:
        return "⏳ Pendiente de autorización. No puedes usar el bot aún."
    if user.status == UserStatus.rechazado:
        return "❌ Acceso rechazado."
    return "No autorizado."


def main() -> None:
    if not settings.bot_alumnos_token:
        raise SystemExit("BOT_ALUMNOS_TOKEN no configurado")

    app = (
        Application.builder()
        .token(settings.bot_alumnos_token)
        .build()
    )

    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre)],
            APELLIDOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_apellidos)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(reg_handler)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("bibliografia", bibliografia_cmd))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CallbackQueryHandler(bibliografia_callback, pattern=r"^bib:\d+$"))
    app.add_handler(CallbackQueryHandler(bibliografia_list_callback, pattern=r"^bib:list$"))
    app.add_handler(CallbackQueryHandler(bibliografia_file_callback, pattern=r"^bibfile:"))
    app.add_handler(CallbackQueryHandler(test_callback, pattern=r"^test:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question))

    logger.info("Bot alumnos iniciado")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
