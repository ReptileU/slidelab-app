"""Перенос данных между компьютером и облаком — туда (push) и обратно (pull, для отката).

    uv run python -m slidelab.tools.cloud_transfer push   # SQLite + папки с компьютера → облачная база
    uv run python -m slidelab.tools.cloud_transfer pull   # облачная база → новый SQLite + папки на компьютере

Откуда и куда — из .env компьютера:
    DATABASE_URL        — база компьютера (sqlite+aiosqlite:///data/slidelab.db)
    CLOUD_DATABASE_URL  — облачная база (строка подключения из Neon)

push перед копированием очищает облачную базу (там ещё нет живых данных — облако не запущено).
pull ничего не стирает: пишет в data/slidelab_from_cloud.db и папку orders_from_cloud/ —
их подставляют вместо старых вручную, когда облако уже выключено (см. CLOUD.md).
"""

import asyncio
import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Table, delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from slidelab.config import normalize_db_url
from slidelab.core.models import Base, StoredFile

BATCH = 500


class _Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///data/slidelab.db"
    cloud_database_url: str = ""
    work_dir: Path = Path("orders")
    data_dir: Path = Path("data")
    content_dir: Path = Path("content")


def _tables() -> list[Table]:
    # stored_files — отдельно (это файлы, а не записи бота); остальное — в порядке внешних ключей
    return [t for t in Base.metadata.sorted_tables if t.name != StoredFile.__tablename__]


async def _migrate(url: str) -> None:
    """Схема целевой базы — последней версии (alembic), как при обычном запуске бота."""
    env = dict(os.environ, DATABASE_URL=url)
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
    if await proc.wait() != 0:
        raise SystemExit("Не удалось обновить схему целевой базы")


async def copy_tables(src: AsyncEngine, dst: AsyncEngine) -> dict[str, int]:
    counts: dict[str, int] = {}
    tables = _tables()
    async with dst.begin() as conn:
        if dst.dialect.name == "postgresql":
            names = ", ".join(f'"{t.name}"' for t in tables)
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        else:
            for table in reversed(tables):
                await conn.execute(delete(table))
    # Циклические ссылки (заказ → купон → заказ, подарок ↔ купон): такие столбцы сначала пустые,
    # а заполняем их, когда все таблицы уже скопированы
    later: dict[str, list[str]] = {t.name: [fk.parent.name for fk in t.foreign_keys if fk.use_alter] for t in tables}
    deferred: list[tuple[Table, list[dict[str, object]]]] = []
    for table in tables:
        async with src.connect() as s:
            rows = [dict(r._mapping) for r in (await s.execute(select(table))).all()]
        cols = later[table.name]
        if cols:
            key_names = [c.name for c in table.primary_key.columns]
            deferred.append(
                (
                    table,
                    [
                        {**{k: r[k] for k in key_names}, **{c: r[c] for c in cols}}
                        for r in rows
                        if any(r[c] is not None for c in cols)
                    ],
                )
            )
            rows = [{**r, **{c: None for c in cols}} for r in rows]
        async with dst.begin() as d:
            for i in range(0, len(rows), BATCH):
                await d.execute(insert(table), rows[i : i + BATCH])
        counts[table.name] = len(rows)
    async with dst.begin() as d:
        for table, values in deferred:
            key_cols = list(table.primary_key.columns)
            keys = {c.name for c in key_cols}
            for v in values:
                stmt = table.update().where(*[c == v[c.name] for c in key_cols])
                await d.execute(stmt.values({k: x for k, x in v.items() if k not in keys}))
    if dst.dialect.name == "postgresql":
        async with dst.begin() as d:
            for table in tables:
                auto = [c for c in table.primary_key.columns if c.autoincrement is not False]
                if len(auto) == 1 and auto[0].type.python_type is int:
                    col = auto[0].name
                    await d.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{col}'), "
                            f'COALESCE((SELECT MAX("{col}") FROM "{table.name}"), 0) + 1, false)'
                        )
                    )
    return counts


async def push_files(dst: AsyncEngine, roots: dict[str, Path]) -> int:
    from slidelab.core.db import make_sessionmaker
    from slidelab.core.filemirror import FileMirror, Root

    async with dst.begin() as conn:
        await conn.execute(delete(StoredFile))
    mirror = FileMirror(make_sessionmaker(dst), [Root(name, path) for name, path in roots.items()])
    written, _ = await mirror.sync()
    return written


async def pull_files(src: AsyncEngine, roots: dict[str, Path]) -> int:
    from slidelab.core.db import make_sessionmaker
    from slidelab.core.filemirror import FileMirror, Root

    return await FileMirror(make_sessionmaker(src), [Root(name, path) for name, path in roots.items()]).restore()


async def _count(engine: AsyncEngine) -> dict[str, int]:
    out = {}
    async with engine.connect() as conn:
        for table in _tables():
            out[table.name] = int(await conn.scalar(select(func.count()).select_from(table)) or 0)
    return out


async def push(env: _Env) -> None:
    if not env.cloud_database_url:
        raise SystemExit("Впишите в .env строку CLOUD_DATABASE_URL=<строка подключения из Neon>")
    src_url, dst_url = normalize_db_url(env.database_url), normalize_db_url(env.cloud_database_url)
    await _migrate(src_url)  # своя база тоже последней версии — столбцы совпадут
    await _migrate(dst_url)
    src, dst = create_async_engine(src_url), create_async_engine(dst_url)
    try:
        counts = await copy_tables(src, dst)
        files = await push_files(dst, {"orders": env.work_dir, "data": env.data_dir, "content": env.content_dir})
        check = await _count(dst)
    finally:
        await src.dispose()
        await dst.dispose()
    bad = {k: (v, check.get(k)) for k, v in counts.items() if check.get(k) != v}
    print(f"Перенесено в облако: {sum(counts.values())} записей, {files} файлов")
    for name, n in counts.items():
        if n:
            print(f"  {name}: {n}")
    if bad:
        raise SystemExit(f"Не совпало количество записей: {bad}")
    print("Готово. Проверка пройдена.")


async def pull(env: _Env) -> None:
    if not env.cloud_database_url:
        raise SystemExit("Впишите в .env строку CLOUD_DATABASE_URL=<строка подключения из Neon>")
    target = env.data_dir / "slidelab_from_cloud.db"
    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    dst_url = f"sqlite+aiosqlite:///{target.as_posix()}"
    await _migrate(dst_url)
    src, dst = create_async_engine(normalize_db_url(env.cloud_database_url)), create_async_engine(dst_url)
    try:
        counts = await copy_tables(src, dst)
        files = await pull_files(
            src,
            {
                "orders": env.work_dir.with_name(env.work_dir.name + "_from_cloud"),
                "data": env.data_dir / "from_cloud",
                "content": env.content_dir.with_name(env.content_dir.name + "_from_cloud"),
            },
        )
    finally:
        await src.dispose()
        await dst.dispose()
    print(f"Скачано из облака: {sum(counts.values())} записей → {target}, {files} файлов")
    print("Как подставить вместо старого — см. CLOUD.md, раздел «Откат».")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("push", "pull"):
        raise SystemExit("Использование: python -m slidelab.tools.cloud_transfer push|pull")
    asyncio.run(push(_Env()) if cmd == "push" else pull(_Env()))


if __name__ == "__main__":
    main()
