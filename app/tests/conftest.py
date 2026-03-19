from __future__ import annotations

import random
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base


@dataclass(slots=True)
class DummyLease:
    acquired: bool = True

    async def release(self) -> None:
        return None


class DummyLockManager:
    async def acquire(self, key: str, ttl_seconds: int) -> DummyLease:
        return DummyLease()


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest.fixture
def settings() -> Settings:
    configured = Settings(BOT_TOKEN="test-token")
    configured.match_base_probability = 1.0
    configured.match_probability_cap = 1.0
    configured.match_wait_bonus = 0.0
    return configured


@pytest.fixture
def rng() -> random.Random:
    return random.Random(7)


@pytest.fixture
def lock_manager() -> DummyLockManager:
    return DummyLockManager()
