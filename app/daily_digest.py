from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.bootstrap import AppContext
from app.bot.formatting import format_daily_digest_message
from app.db.base import session_scope
from app.db.models import TelegramGroup
from app.db.repositories.daily_digest_repo import PENDING_RETRY_AFTER, DailyDigestRepository
from app.domain.models.daily_digest import DailyDigestStatus
from app.domain.services.daily_digest_facts_service import DailyDigestFactsService
from app.domain.services.daily_digest_summary_service import DailyDigestSummaryService
from app.logging import logger


@dataclass(slots=True)
class DailyDigestDispatchResult:
    group_title: str
    telegram_group_id: int
    digest_day: date
    status: str
    reason: str | None = None
    message_id: int | None = None


async def list_due_digest_groups(
    app_context: AppContext,
    *,
    digest_day: date,
    now: datetime,
    limit: int,
) -> list[TelegramGroup]:
    async with session_scope(app_context.session_factory) as session:
        return await DailyDigestRepository(session).list_due_groups(
            digest_day=digest_day,
            now=now,
            limit=limit,
        )


async def send_digest_for_group(
    app_context: AppContext,
    *,
    group: TelegramGroup,
    digest_day: date,
    now: datetime,
) -> DailyDigestDispatchResult:
    summary_result = None
    summary_text = None

    try:
        async with session_scope(app_context.session_factory) as session:
            async with session.begin():
                repo = DailyDigestRepository(session)
                existing = await repo.get_by_group_day(group_id=group.id, digest_day=digest_day, for_update=True)
                if existing is not None:
                    if existing.status == DailyDigestStatus.SENT:
                        return DailyDigestDispatchResult(
                            group_title=group.title,
                            telegram_group_id=group.telegram_group_id,
                            digest_day=digest_day,
                            status="skipped",
                            reason="already_sent",
                        )
                    if existing.status == DailyDigestStatus.PENDING and existing.updated_at > now - PENDING_RETRY_AFTER:
                        return DailyDigestDispatchResult(
                            group_title=group.title,
                            telegram_group_id=group.telegram_group_id,
                            digest_day=digest_day,
                            status="skipped",
                            reason="already_running",
                        )

                facts = await DailyDigestFactsService(session).build_for_group(
                    group_id=group.id,
                    digest_day=digest_day,
                    now=now,
                )
                if not facts.leaderboard:
                    return DailyDigestDispatchResult(
                        group_title=group.title,
                        telegram_group_id=group.telegram_group_id,
                        digest_day=digest_day,
                        status="skipped",
                        reason="no_pigs",
                    )

                await repo.claim_pending(
                    group_id=group.id,
                    digest_day=digest_day,
                    now=now,
                    source_payload=facts.to_payload(),
                )

        summary_result = await DailyDigestSummaryService(app_context.settings).generate_summary(facts)
        summary_text = format_daily_digest_message(facts, summary_result.text)
        sent_message = await app_context.bot.send_message(group.telegram_group_id, summary_text)

        async with session_scope(app_context.session_factory) as session:
            async with session.begin():
                repo = DailyDigestRepository(session)
                digest = await repo.get_by_group_day(group_id=group.id, digest_day=digest_day, for_update=True)
                if digest is None:
                    return DailyDigestDispatchResult(
                        group_title=group.title,
                        telegram_group_id=group.telegram_group_id,
                        digest_day=digest_day,
                        status="failed",
                        reason="missing_digest_row",
                    )
                await repo.mark_sent(
                    digest,
                    summary_text=summary_text,
                    llm_model=summary_result.llm_model,
                    sent_at=now,
                    telegram_message_id=getattr(sent_message, "message_id", None),
                )

        return DailyDigestDispatchResult(
            group_title=group.title,
            telegram_group_id=group.telegram_group_id,
            digest_day=digest_day,
            status="sent",
            message_id=getattr(sent_message, "message_id", None),
        )
    except Exception as exc:
        logger.exception("Daily digest failed for group %s on %s", group.id, digest_day)
        async with session_scope(app_context.session_factory) as session:
            async with session.begin():
                repo = DailyDigestRepository(session)
                digest = await repo.get_by_group_day(group_id=group.id, digest_day=digest_day, for_update=True)
                if digest is not None:
                    await repo.mark_failed(
                        digest,
                        summary_text=summary_text,
                        llm_model=summary_result.llm_model if summary_result is not None else None,
                        error_text=str(exc),
                        now=now,
                    )
        return DailyDigestDispatchResult(
            group_title=group.title,
            telegram_group_id=group.telegram_group_id,
            digest_day=digest_day,
            status="failed",
            reason=str(exc),
        )
