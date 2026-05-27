import logging

import httpx

from shared.config import get_settings

logger = logging.getLogger(__name__)


async def notify_telegram_user(bot_token: str, chat_id: int, text: str) -> bool:
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.exception("Error notificando usuario %s: %s", chat_id, e)
            return False


async def notify_admins(text: str, reply_markup: dict | None = None) -> None:
    settings = get_settings()
    if not settings.bot_admin_token or not settings.admin_ids:
        logger.warning("No se puede notificar: falta BOT_ADMIN_TOKEN o ADMIN_TELEGRAM_IDS")
        return
    url = f"https://api.telegram.org/bot{settings.bot_admin_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        for admin_id in settings.admin_ids:
            payload: dict = {"chat_id": admin_id, "text": text, "parse_mode": "Markdown"}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            except Exception as e:
                logger.exception("Error notificando admin %s: %s", admin_id, e)
