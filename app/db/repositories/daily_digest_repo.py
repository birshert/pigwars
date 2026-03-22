from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroupDailyDigest, Pig, TelegramGroup
from app.domain.models.daily_digest import DailyDigestStatus


PENDING_RETRY_AFTER = timedelta(minutes=15)


class DailyDigestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_due_groups(
        self,
        *,
        digest_day: date,
        now: datetime,
        limit: int,
        allowed_telegram_group_ids: Sequence[int] | None = None,
    ) -> list[TelegramGroup]:
        stale_before = now - PENDING_RETRY_AFTER
        stmt = (
            select(TelegramGroup)
            .join(Pig, Pig.group_id == TelegramGroup.id)
            .outerjoin(
                GroupDailyDigest,
                and_(
                    GroupDailyDigest.group_id == TelegramGroup.id,
                    GroupDailyDigest.digest_day == digest_day,
                ),
            )
            .where(
                or_(
                    GroupDailyDigest.id.is_(None),
                    GroupDailyDigest.status.in_((DailyDigestStatus.FAILED, DailyDigestStatus.SKIPPED)),
                    and_(
                        GroupDailyDigest.status == DailyDigestStatus.PENDING,
                        GroupDailyDigest.updated_at <= stale_before,
                    ),
                )
            )
            .order_by(TelegramGroup.id.asc())
            .distinct()
            .limit(limit)
        )
        if allowed_telegram_group_ids:
            stmt = stmt.where(TelegramGroup.telegram_group_id.in_(list(allowed_telegram_group_ids)))
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_by_group_day(
        self,
        *,
        group_id: int,
        digest_day: date,
        for_update: bool = False,
    ) -> GroupDailyDigest | None:
        stmt = select(GroupDailyDigest).where(
            GroupDailyDigest.group_id == group_id,
            GroupDailyDigest.digest_day == digest_day,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self._session.scalar(stmt)

    async def claim_pending(
        self,
        *,
        group_id: int,
        digest_day: date,
        now: datetime,
        source_payload: dict[str, object],
    ) -> GroupDailyDigest:
        digest = await self.get_by_group_day(group_id=group_id, digest_day=digest_day, for_update=True)
        if digest is None:
            digest = GroupDailyDigest(
                group_id=group_id,
                digest_day=digest_day,
                status=DailyDigestStatus.PENDING,
                source_payload=source_payload,
                updated_at=now,
            )
            self._session.add(digest)
            await self._session.flush()
            return digest

        digest.status = DailyDigestStatus.PENDING
        digest.source_payload = source_payload
        digest.summary_text = None
        digest.llm_model = None
        digest.sent_at = None
        digest.telegram_message_id = None
        digest.error_text = None
        digest.updated_at = now
        await self._session.flush()
        return digest

    async def mark_sent(
        self,
        digest: GroupDailyDigest,
        *,
        summary_text: str,
        llm_model: str | None,
        sent_at: datetime,
        telegram_message_id: int | None,
    ) -> None:
        digest.status = DailyDigestStatus.SENT
        digest.summary_text = summary_text
        digest.llm_model = llm_model
        digest.sent_at = sent_at
        digest.telegram_message_id = telegram_message_id
        digest.error_text = None
        digest.updated_at = sent_at

    async def mark_failed(
        self,
        digest: GroupDailyDigest,
        *,
        summary_text: str | None,
        llm_model: str | None,
        error_text: str,
        now: datetime,
    ) -> None:
        digest.status = DailyDigestStatus.FAILED
        digest.summary_text = summary_text
        digest.llm_model = llm_model
        digest.sent_at = None
        digest.telegram_message_id = None
        digest.error_text = error_text
        digest.updated_at = now
