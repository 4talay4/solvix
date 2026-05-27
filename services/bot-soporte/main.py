import logging
import sys
from enum import Enum
from pathlib import Path

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config import get_settings
from shared.db import AsyncSessionLocal
from shared.models import SupportType
from shared.notify import notify_admins
from shared.repository import create_support_ticket, get_user_by_telegram_id, log_activity

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

TIPO, MENSAJE = range(2)

HELP_SOPORTE = """🆘 *Bot de soporte del curso*

/start — Iniciar
/help — Esta ayuda
/cancelar — Cancelar el envío en curso

Puedes enviar:
• 💡 Ideas de mejora del proyecto
• 🐛 Incidencias de funcionamiento"""


class TicketType(str, Enum):
    mejora = "💡 Idea de mejora"
    incidencia = "🐛 Incidencia"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END
    keyboard = ReplyKeyboardMarkup(
        [[TicketType.mejora.value, TicketType.incidencia.value]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        "Selecciona el tipo de mensaje:",
        reply_markup=keyboard,
    )
    return TIPO


async def elegir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return TIPO
    text = update.message.text
    if text == TicketType.mejora.value:
        context.user_data["ticket_type"] = SupportType.mejora
    elif text == TicketType.incidencia.value:
        context.user_data["ticket_type"] = SupportType.incidencia
    else:
        await update.message.reply_text("Elige una opción del teclado o /cancelar")
        return TIPO
    await update.message.reply_text(
        "Escribe tu mensaje con el mayor detalle posible:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return MENSAJE


async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_tg = update.effective_user
    if not user_tg or not update.message or not update.message.text:
        return MENSAJE

    ticket_type = context.user_data.get("ticket_type")
    if not ticket_type:
        await update.message.reply_text("Usa /start para comenzar de nuevo.")
        return ConversationHandler.END

    mensaje = update.message.text.strip()
    display = " ".join(
        p
        for p in [user_tg.first_name or "", user_tg.last_name or ""]
        if p
    ).strip() or f"Usuario {user_tg.id}"

    async with AsyncSessionLocal() as session:
        db_user = await get_user_by_telegram_id(session, user_tg.id)
        ticket = await create_support_ticket(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            display_name=display,
            ticket_type=ticket_type,
            message=mensaje,
            user_id=db_user.id if db_user else None,
        )
        await log_activity(
            session,
            "soporte_enviado",
            telegram_id=user_tg.id,
            user_id=db_user.id if db_user else None,
            detail=f"{ticket_type.value}: {mensaje[:100]}",
            metadata={"ticket_id": ticket.id},
        )
        await session.commit()
        ticket_id = ticket.id

    await update.message.reply_text(
        f"✅ Mensaje registrado (ticket #{ticket_id}).\n"
        "El administrador lo revisará. Gracias.",
    )

    admin_text = (
        f"🆘 *Nuevo ticket de soporte #{ticket_id}*\n"
        f"Tipo: *{ticket_type.value}*\n"
        f"Usuario: {display}\n"
        f"Telegram: `{user_tg.id}` @{user_tg.username or '-'}\n\n"
        f"{mensaje}"
    )
    await notify_admins(admin_text)

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_SOPORTE, parse_mode="Markdown")


def main() -> None:
    if not settings.bot_soporte_token:
        raise SystemExit("BOT_SOPORTE_TOKEN no configurado")

    app = Application.builder().token(settings.bot_soporte_token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_tipo)],
            MENSAJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar), CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancelar", cancelar))

    logger.info("Bot soporte iniciado")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
