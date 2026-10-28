import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slidelab.core.models import Base, User
from slidelab.core.seed import seed


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


# По умолчанию — SQLite в памяти. Для проверки на PostgreSQL:
# TEST_DATABASE_URL=postgresql+asyncpg://slidelab:slidelab@localhost:5433/slidelab_test uv run pytest
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await seed(s)
        yield s
    await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_user(session: AsyncSession) -> Callable[..., object]:
    counter = iter(range(1000, 10_000))

    async def _make(**kwargs: object) -> User:
        user = User(tg_id=next(counter), first_name="Тест", **kwargs)
        session.add(user)
        await session.flush()
        return user

    return _make
