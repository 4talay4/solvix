from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import (
    ActivityLog,
    QuestionHistory,
    QuestionsCache,
    SupportStatus,
    SupportTicket,
    SupportType,
    User,
    UserStatus,
)


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_or_touch_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        user.telegram_username = username
        user.first_name = first_name
        user.last_name = last_name
        return user
    user = User(
        telegram_id=telegram_id,
        telegram_username=username,
        first_name=first_name,
        last_name=last_name,
        status=UserStatus.registrando,
    )
    session.add(user)
    await session.flush()
    return user


async def complete_registration(
    session: AsyncSession, user: User, nombre: str, apellidos: str
) -> User:
    user.nombre = nombre.strip()
    user.apellidos = apellidos.strip()
    user.status = UserStatus.pendiente
    user.registered_at = datetime.now(timezone.utc)
    return user


async def set_user_status(session: AsyncSession, user: User, status: UserStatus) -> User:
    user.status = status
    now = datetime.now(timezone.utc)
    if status == UserStatus.autorizado:
        user.authorized_at = now
    elif status == UserStatus.rechazado:
        user.rejected_at = now
    return user


async def log_activity(
    session: AsyncSession,
    action: str,
    telegram_id: int | None = None,
    user_id: int | None = None,
    detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    session.add(
        ActivityLog(
            user_id=user_id,
            telegram_id=telegram_id,
            action=action,
            detail=detail,
            metadata_json=metadata or {},
        )
    )


async def list_pending_users(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).where(User.status == UserStatus.pendiente).order_by(User.registered_at)
    )
    return list(result.scalars().all())


async def list_users(session: AsyncSession, limit: int = 50) -> list[User]:
    result = await session.execute(select(User).order_by(User.id.desc()).limit(limit))
    return list(result.scalars().all())


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def save_question_history(
    session: AsyncSession,
    user_id: int | None,
    question: str,
    answer: str,
    from_cache: bool,
    sources: list,
) -> None:
    session.add(
        QuestionHistory(
            user_id=user_id,
            question_text=question,
            answer_text=answer,
            from_cache=from_cache,
            sources_json=sources,
        )
    )


async def get_cache_candidates(session: AsyncSession, limit: int | None = None) -> list[QuestionsCache]:
    from shared.config import get_settings

    cap = limit or get_settings().cache_lookup_limit
    result = await session.execute(
        select(QuestionsCache)
        .order_by(QuestionsCache.hit_count.desc(), QuestionsCache.last_used_at.desc())
        .limit(cap)
    )
    return list(result.scalars().all())


async def get_all_cache_entries(session: AsyncSession) -> list[QuestionsCache]:
    return await get_cache_candidates(session)


async def upsert_cache_entry(
    session: AsyncSession,
    question: str,
    normalized: str,
    answer: str,
    sources: list,
    embedding: list[float] | None,
) -> QuestionsCache:
    entry = QuestionsCache(
        question_text=question,
        question_normalized=normalized,
        answer_text=answer,
        sources_json=sources,
        embedding_json=embedding,
    )
    session.add(entry)
    await session.flush()
    return entry


async def bump_cache_hit(session: AsyncSession, entry_id: int) -> None:
    await session.execute(
        update(QuestionsCache)
        .where(QuestionsCache.id == entry_id)
        .values(
            hit_count=QuestionsCache.hit_count + 1,
            last_used_at=datetime.now(timezone.utc),
        )
    )


async def create_support_ticket(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    display_name: str,
    ticket_type: SupportType,
    message: str,
    user_id: int | None = None,
) -> SupportTicket:
    ticket = SupportTicket(
        user_id=user_id,
        telegram_id=telegram_id,
        telegram_username=username,
        user_display_name=display_name,
        ticket_type=ticket_type,
        message=message,
        status=SupportStatus.abierto,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def list_open_support(session: AsyncSession, limit: int = 20) -> list[SupportTicket]:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status == SupportStatus.abierto)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_support_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket | None:
    return await session.get(SupportTicket, ticket_id)


async def close_support_ticket(session: AsyncSession, ticket_id: int) -> bool:
    ticket = await get_support_ticket(session, ticket_id)
    if not ticket or ticket.status != SupportStatus.abierto:
        return False
    ticket.status = SupportStatus.cerrado
    ticket.closed_at = datetime.now(timezone.utc)
    return True


async def resolve_support_ticket(
    session: AsyncSession,
    ticket_id: int,
    resolution: str,
    admin_telegram_id: int,
) -> SupportTicket | None:
    ticket = await get_support_ticket(session, ticket_id)
    if not ticket or ticket.status != SupportStatus.abierto:
        return None
    ticket.status = SupportStatus.resuelto
    ticket.resolution_message = resolution.strip()
    ticket.resolved_by = admin_telegram_id
    now = datetime.now(timezone.utc)
    ticket.resolved_at = now
    ticket.closed_at = now
    return ticket


async def stats_summary(session: AsyncSession) -> dict:
    users_total = await session.scalar(select(func.count()).select_from(User))
    users_auth = await session.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.autorizado)
    )
    users_pending = await session.scalar(
        select(func.count()).select_from(User).where(User.status == UserStatus.pendiente)
    )
    questions_total = await session.scalar(select(func.count()).select_from(QuestionHistory))
    cache_hits = await session.scalar(
        select(func.count()).select_from(QuestionHistory).where(QuestionHistory.from_cache.is_(True))
    )
    support_open = await session.scalar(
        select(func.count())
        .select_from(SupportTicket)
        .where(SupportTicket.status == SupportStatus.abierto)
    )
    return {
        "users_total": users_total or 0,
        "users_authorized": users_auth or 0,
        "users_pending": users_pending or 0,
        "questions_total": questions_total or 0,
        "questions_from_cache": cache_hits or 0,
        "support_open": support_open or 0,
    }


async def recent_activity(session: AsyncSession, limit: int = 15) -> list[ActivityLog]:
    result = await session.execute(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
