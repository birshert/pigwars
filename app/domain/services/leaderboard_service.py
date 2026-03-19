from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.group_repo import GroupRepository
from app.db.repositories.pig_repo import PigRepository
from app.schemas.leaderboard import LeaderboardEntry


def _build_owner_label(user) -> str:
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    if full_name:
        return full_name
    if user.username:
        return user.username
    return str(user.telegram_user_id)


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._groups = GroupRepository(session)
        self._pigs = PigRepository(session)

    async def get_weight_leaderboard(self, *, telegram_group_id: int, limit: int = 10) -> list[LeaderboardEntry]:
        group = await self._groups.get_by_telegram_id(telegram_group_id)
        if group is None:
            return []

        rows = await self._pigs.list_weight_leaderboard(group_id=group.id, limit=limit)
        return [
            LeaderboardEntry(
                place=index,
                pig_name=pig.name,
                owner_label=_build_owner_label(user),
                weight_kg=pig.weight_kg,
                wins=pig.wins,
                losses=pig.losses,
            )
            for index, (pig, user) in enumerate(rows, start=1)
        ]
