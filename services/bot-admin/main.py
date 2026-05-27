import logging
import sys
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
from shared.notify import notify_telegram_user
from shared.repository import (
    close_support_ticket,
    get_support_ticket,
    get_user_by_id,
    get_user_by_telegram_id,
    list_open_support,
    list_pending_users,
    list_users,
    log_activity,
    recent_activity,
    resolve_support_ticket,
    set_user_status,
    stats_summary,
)
from shared.utils import user_display_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

RESOLVE_MSG = 0

HELP_ADMIN = """🛠 *Bot de administración*

*Acceso:*
/start — Iniciar
/help — Esta ayuda

*Usuarios:*
/pendientes — Solicitudes pendientes
/usuarios — Últimos usuarios registrados
/usuario `<id>` — Detalle de usuario (id de BD)
/autorizar `<telegram_id>` — Aprobar acceso
/rechazar `<telegram_id>` — Denegar acceso

*Monitorización:*
/stats — Estadísticas generales
/logs — Actividad reciente

*Soporte:*
/soporte — Tickets abiertos
/ticket `<id>` — Ver detalle de un ticket
/resolver `<id>` — Resolver ticket con respuesta al usuario
/cerrar `<ticket_id>` — Cerrar sin notificar al usuario

Los botones ✅/❌ en notificaciones gestionan accesos.
El botón *Resolver* en tickets pide la respuesta y notifica al usuario por el bot de soporte."""


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


async def guard_admin(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    if not is_admin(uid):
        if update.message:
            await update.message.reply_text("⛔ No tienes permisos de administrador.")
        elif update.callback_query:
            await update.callback_query.answer("Sin permisos", show_alert=True)
        return False
    return True


async def notify_student(telegram_id: int, text: str) -> None:
    if not settings.bot_alumnos_token:
        return
    url = f"https://api.telegram.org/bot{settings.bot_alumnos_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(url, json={"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    await update.message.reply_text(
        "👋 Panel de administración del curso.\n\n" + HELP_ADMIN,
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    await update.message.reply_text(HELP_ADMIN, parse_mode="Markdown")


async def pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    async with AsyncSessionLocal() as session:
        users = await list_pending_users(session)
    if not users:
        await update.message.reply_text("No hay solicitudes pendientes.")
        return
    for u in users:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Aceptar", callback_data=f"auth:accept:{u.telegram_id}"),
                    InlineKeyboardButton("❌ Rechazar", callback_data=f"auth:reject:{u.telegram_id}"),
                ]
            ]
        )
        text = (
            f"⏳ *Pendiente* — DB id: `{u.id}`\n"
            f"Telegram: `{u.telegram_id}` @{u.telegram_username or '-'}\n"
            f"Nombre: *{user_display_name(u)}*\n"
            f"Registro: {u.registered_at}"
        )
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    async with AsyncSessionLocal() as session:
        users = await list_users(session, limit=30)
    lines = ["👥 *Últimos usuarios*\n"]
    for u in users:
        lines.append(
            f"`{u.id}` | {user_display_name(u)} | {u.status.value} | tg:{u.telegram_id}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def usuario_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /usuario <id_bd>")
        return
    user_id = int(context.args[0])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, user_id)
    if not u:
        await update.message.reply_text("Usuario no encontrado.")
        return
    text = (
        f"👤 *Usuario #{u.id}*\n"
        f"Estado: *{u.status.value}*\n"
        f"Telegram ID: `{u.telegram_id}`\n"
        f"Username: @{u.telegram_username or '-'}\n"
        f"Nombre: {user_display_name(u)}\n"
        f"Registro: {u.registered_at}\n"
        f"Autorizado: {u.authorized_at or '-'}\n"
        f"Rechazado: {u.rejected_at or '-'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def autorizar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /autorizar <telegram_id>")
        return
    tg_id = int(context.args[0])
    await _process_auth(update, tg_id, accept=True)


async def rechazar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /rechazar <telegram_id>")
        return
    tg_id = int(context.args[0])
    await _process_auth(update, tg_id, accept=False)


async def _process_auth(update: Update, telegram_id: int, accept: bool) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            msg = "Usuario no encontrado."
            if update.message:
                await update.message.reply_text(msg)
            return
        new_status = UserStatus.autorizado if accept else UserStatus.rechazado
        await set_user_status(session, user, new_status)
        await log_activity(
            session,
            "autorizado" if accept else "rechazado",
            user_id=user.id,
            telegram_id=telegram_id,
            detail=f"por admin {update.effective_user.id if update.effective_user else '?'}",
        )
        await session.commit()
        name = user_display_name(user)

    if accept:
        await notify_student(
            telegram_id,
            f"✅ ¡Bienvenido/a, {name}!\n\n"
            "Tu acceso ha sido *autorizado*. Puedes hacer preguntas del temario en lenguaje natural.\n"
            "Comandos: /help · /bibliografia · /test",
        )
        result = f"✅ Usuario {name} (`{telegram_id}`) autorizado."
    else:
        await notify_student(
            telegram_id,
            "❌ Tu solicitud de acceso al bot del curso ha sido rechazada.",
        )
        result = f"❌ Usuario {name} (`{telegram_id}`) rechazado."

    if update.message:
        await update.message.reply_text(result, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            update.callback_query.message.text + f"\n\n{result}",
            parse_mode="Markdown",
        )


async def auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not is_admin(query.from_user.id):
        await query.answer("Sin permisos", show_alert=True)
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    action, tg_id_str = parts[1], parts[2]
    accept = action == "accept"
    await _process_auth(update, int(tg_id_str), accept=accept)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    async with AsyncSessionLocal() as session:
        s = await stats_summary(session)
    text = (
        "📊 *Estadísticas*\n\n"
        f"Usuarios totales: *{s['users_total']}*\n"
        f"Autorizados: *{s['users_authorized']}*\n"
        f"Pendientes: *{s['users_pending']}*\n"
        f"Preguntas totales: *{s['questions_total']}*\n"
        f"Desde caché: *{s['questions_from_cache']}*\n"
        f"Soporte abierto: *{s['support_open']}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    async with AsyncSessionLocal() as session:
        logs = await recent_activity(session, limit=20)
    if not logs:
        await update.message.reply_text("Sin actividad registrada.")
        return
    lines = ["📋 *Actividad reciente*\n"]
    for log in logs:
        lines.append(
            f"`{log.created_at:%Y-%m-%d %H:%M}` | {log.action} | tg:{log.telegram_id or '-'} | {log.detail or ''}"[:120]
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Resolver", callback_data=f"ticket:resolve:{ticket_id}"),
                InlineKeyboardButton("🚫 Cerrar", callback_data=f"ticket:close:{ticket_id}"),
            ]
        ]
    )


def _format_ticket(t) -> str:
    return (
        f"🎫 *Ticket #{t.id}* ({t.ticket_type.value})\n"
        f"Usuario: {t.user_display_name} (`{t.telegram_id}`)\n"
        f"Fecha: {t.created_at}\n\n"
        f"*Mensaje:*\n{t.message}"
    )


async def soporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    async with AsyncSessionLocal() as session:
        tickets = await list_open_support(session)
    if not tickets:
        await update.message.reply_text("No hay tickets de soporte abiertos.")
        return
    for t in tickets:
        await update.message.reply_text(
            _format_ticket(t),
            parse_mode="Markdown",
            reply_markup=_ticket_keyboard(t.id),
        )


async def ticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /ticket <ticket_id>")
        return
    ticket_id = int(context.args[0])
    async with AsyncSessionLocal() as session:
        t = await get_support_ticket(session, ticket_id)
    if not t:
        await update.message.reply_text("Ticket no encontrado.")
        return
    text = _format_ticket(t)
    if t.status.value != "abierto":
        text += f"\n\nEstado: *{t.status.value}*"
        if t.resolution_message:
            text += f"\n\n*Resolución:*\n{t.resolution_message}"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=_ticket_keyboard(t.id),
    )


async def start_resolver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await guard_admin(update):
        return ConversationHandler.END
    if not context.args:
        await update.message.reply_text(
            "Uso: /resolver <ticket_id>\n\n"
            "También puedes pulsar *Resolver* en /soporte.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    ticket_id = int(context.args[0])
    async with AsyncSessionLocal() as session:
        t = await get_support_ticket(session, ticket_id)
    if not t or t.status.value != "abierto":
        await update.message.reply_text("Ticket no encontrado o ya gestionado.")
        return ConversationHandler.END
    context.user_data["resolve_ticket_id"] = ticket_id
    await update.message.reply_text(
        f"✍️ Escribe la *respuesta de resolución* para el ticket #{ticket_id}.\n"
        f"El usuario recibirá esta respuesta por el bot de soporte.\n\n"
        f"_Incidencia:_ {t.message[:200]}{'…' if len(t.message) > 200 else ''}",
        parse_mode="Markdown",
    )
    return RESOLVE_MSG


async def start_resolver_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query or not query.data:
        return ConversationHandler.END
    if not is_admin(query.from_user.id):
        await query.answer("Sin permisos", show_alert=True)
        return ConversationHandler.END
    ticket_id = int(query.data.split(":")[2])
    async with AsyncSessionLocal() as session:
        t = await get_support_ticket(session, ticket_id)
    if not t or t.status.value != "abierto":
        await query.answer("Ticket ya gestionado", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["resolve_ticket_id"] = ticket_id
    await query.message.reply_text(
        f"✍️ Escribe la respuesta de resolución para el ticket #{ticket_id}.\n"
        "El usuario será notificado automáticamente.",
    )
    return RESOLVE_MSG


async def receive_resolution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await guard_admin(update):
        return ConversationHandler.END
    if not update.message or not update.message.text:
        return RESOLVE_MSG

    ticket_id = context.user_data.get("resolve_ticket_id")
    if not ticket_id:
        await update.message.reply_text("Sesión expirada. Usa /resolver <id> de nuevo.")
        return ConversationHandler.END

    resolution = update.message.text.strip()
    admin_id = update.effective_user.id if update.effective_user else 0

    async with AsyncSessionLocal() as session:
        ticket = await resolve_support_ticket(session, ticket_id, resolution, admin_id)
        if not ticket:
            await update.message.reply_text("No se pudo resolver el ticket (ya cerrado o inexistente).")
            context.user_data.pop("resolve_ticket_id", None)
            return ConversationHandler.END
        await log_activity(
            session,
            "ticket_resuelto",
            telegram_id=ticket.telegram_id,
            detail=f"ticket #{ticket_id}",
            metadata={"admin_id": admin_id},
        )
        await session.commit()
        user_tg = ticket.telegram_id
        tipo = ticket.ticket_type.value
        original = ticket.message

    context.user_data.pop("resolve_ticket_id", None)

    user_msg = (
        f"✅ *Ticket #{ticket_id} resuelto*\n\n"
        f"Tipo: {tipo}\n"
        f"*Tu mensaje:*\n{original}\n\n"
        f"*Respuesta del equipo:*\n{resolution}"
    )
    sent = await notify_telegram_user(settings.bot_soporte_token, user_tg, user_msg)

    if sent:
        await update.message.reply_text(
            f"✅ Ticket #{ticket_id} resuelto y usuario notificado.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"✅ Ticket #{ticket_id} resuelto, pero *no se pudo notificar* al usuario.\n"
            f"Comunica manualmente a `{user_tg}`.",
            parse_mode="Markdown",
        )
    return ConversationHandler.END


async def cancel_resolver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("resolve_ticket_id", None)
    if update.message:
        await update.message.reply_text("Resolución cancelada.")
    return ConversationHandler.END


async def cerrar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Uso: /cerrar <ticket_id>")
        return
    ticket_id = int(context.args[0])
    async with AsyncSessionLocal() as session:
        ok = await close_support_ticket(session, ticket_id)
        await session.commit()
    await update.message.reply_text("Ticket cerrado." if ok else "Ticket no encontrado o ya cerrado.")


async def ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not is_admin(query.from_user.id):
        await query.answer("Sin permisos", show_alert=True)
        return
    ticket_id = int(query.data.split(":")[2])
    async with AsyncSessionLocal() as session:
        ok = await close_support_ticket(session, ticket_id)
        await session.commit()
    await query.answer("Cerrado" if ok else "Error")
    if ok and query.message:
        await query.edit_message_text(query.message.text + "\n\n✅ *Cerrado*", parse_mode="Markdown")


def main() -> None:
    if not settings.bot_admin_token:
        raise SystemExit("BOT_ADMIN_TOKEN no configurado")
    if not settings.admin_ids:
        raise SystemExit("ADMIN_TELEGRAM_IDS no configurado")

    app = Application.builder().token(settings.bot_admin_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("pendientes", pendientes))
    app.add_handler(CommandHandler("usuarios", usuarios))
    app.add_handler(CommandHandler("usuario", usuario_cmd))
    app.add_handler(CommandHandler("autorizar", autorizar_cmd))
    app.add_handler(CommandHandler("rechazar", rechazar_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("soporte", soporte_cmd))
    app.add_handler(CommandHandler("ticket", ticket_cmd))
    app.add_handler(CommandHandler("cerrar", cerrar_cmd))

    resolve_conv = ConversationHandler(
        entry_points=[
            CommandHandler("resolver", start_resolver),
            CallbackQueryHandler(start_resolver_callback, pattern=r"^ticket:resolve:"),
        ],
        states={
            RESOLVE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_resolution)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_resolver)],
        allow_reentry=True,
    )
    app.add_handler(resolve_conv)

    app.add_handler(CallbackQueryHandler(auth_callback, pattern=r"^auth:"))
    app.add_handler(CallbackQueryHandler(ticket_callback, pattern=r"^ticket:"))

    logger.info("Bot admin iniciado. Admins: %s", settings.admin_ids)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
