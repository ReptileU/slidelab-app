import asyncio

from alembic import context
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from slidelab.config import Settings
from slidelab.core.models import Base

target_metadata = Base.metadata


class _DbSettings(BaseSettings):
    """Миграциям токен бота не нужен — берём только адрес БД, из окружения или .env, как бот и seed."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = Settings.model_fields["database_url"].default


DATABASE_URL = _DbSettings().database_url


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,  # будущие миграции сразу пригодны и для SQLite
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
