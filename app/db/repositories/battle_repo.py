from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Battle


class BattleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        group_id: int,
        pig1_id: UUID,
        pig2_id: UUID,
        winner_pig_id: UUID,
        loser_pig_id: UUID,
        pig1_score: Decimal,
        pig2_score: Decimal,
        weight_delta_winner: Decimal,
        weight_delta_loser: Decimal,
    ) -> Battle:
        battle = Battle(
            group_id=group_id,
            pig1_id=pig1_id,
            pig2_id=pig2_id,
            winner_pig_id=winner_pig_id,
            loser_pig_id=loser_pig_id,
            pig1_score=pig1_score,
            pig2_score=pig2_score,
            weight_delta_winner=weight_delta_winner,
            weight_delta_loser=weight_delta_loser,
        )
        self._session.add(battle)
        await self._session.flush()
        return battle
