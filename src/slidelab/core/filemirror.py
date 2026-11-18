"""Зеркало файлов в базе: папка конвейера (orders/) и служебные файлы (data/) переживают перезапуск облака.

На бесплатных облаках диск временный — при каждом перезапуске и выкладке он чистый. Поэтому:
- при запуске restore() раскладывает файлы из базы обратно на диск;
- каждые несколько секунд sync() записывает в базу новые и изменённые файлы и удаляет пропавшие.

Код конвейера при этом работает с обычной папкой, как на компьютере.
Слишком большие файлы (готовые презентации больше MAX_FILE) в базу не кладём: они уже ушли клиенту в Telegram.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.core.models import StoredFile
from slidelab.core.models.base import utcnow

log = logging.getLogger(__name__)

MAX_FILE = 15 * 1024 * 1024  # бесплатная база — 1 ГБ; большие готовые файлы хранит Telegram
SYNC_EVERY = 10  # секунд
# Базы, журналы и недописанные файлы не копируем
SKIP_SUFFIXES = (".db", ".db-journal", ".db-wal", ".db-shm", ".log", ".part", ".tmp")
SKIP_DIRS = {"logs", "from_cloud", "__pycache__"}


@dataclass(frozen=True, slots=True)
class Root:
    name: str  # префикс в базе: "orders", "data"
    path: Path


def _scan(roots: list[Root]) -> dict[str, tuple[Path, float, int]]:
    found: dict[str, tuple[Path, float, int]] = {}
    for root in roots:
        if not root.path.is_dir():
            continue
        for file in root.path.rglob("*"):
            if not file.is_file() or file.name.endswith(SKIP_SUFFIXES):
                continue
            if SKIP_DIRS.intersection(file.relative_to(root.path).parts[:-1]):
                continue
            st = file.stat()
            if st.st_size > MAX_FILE:
                continue
            key = f"{root.name}/{file.relative_to(root.path).as_posix()}"
            found[key] = (file, st.st_mtime, st.st_size)
    return found


class FileMirror:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], roots: list[Root]) -> None:
        self.sm = sessionmaker
        self.roots = roots
        self.known: dict[str, float] = {}  # путь → mtime, уже лежащий в базе

    def _target(self, key: str) -> Path | None:
        name, _, rel = key.partition("/")
        root = next((r for r in self.roots if r.name == name), None)
        if root is None or not rel or ".." in Path(rel).parts:
            return None
        return root.path / rel

    async def restore(self) -> int:
        """База → диск. Вызывать при запуске, до того как бот начнёт работать с папками."""
        async with self.sm() as session:
            rows = (await session.execute(select(StoredFile.path, StoredFile.data, StoredFile.mtime))).all()
        count = 0
        for key, data, mtime in rows:
            target = self._target(key)
            if target is None:
                continue
            # файл из новой выкладки (например, посты в content/) свежее копии в базе — его не трогаем
            if target.is_file() and target.stat().st_mtime >= mtime:
                continue
            await asyncio.to_thread(_write, target, data, mtime)
            self.known[key] = mtime
            count += 1
        log.info("Файлы восстановлены из базы: %s", count)
        return count

    async def sync(self) -> tuple[int, int]:
        """Диск → база: новые и изменённые файлы записываем, удалённые — убираем. Возвращает (записано, удалено)."""
        found = await asyncio.to_thread(_scan, self.roots)
        changed = [k for k, (_, mtime, _) in found.items() if self.known.get(k) != mtime]
        gone = [k for k in self.known if k not in found]
        if not changed and not gone:
            return 0, 0
        async with self.sm() as session:
            for key in changed:
                path, mtime, size = found[key]
                try:
                    data = await asyncio.to_thread(path.read_bytes)
                except OSError:
                    continue  # файл как раз переносят — заберём в следующий раз
                await session.merge(StoredFile(path=key, data=data, size=size, mtime=mtime, updated_at=utcnow()))
            if gone:
                await session.execute(delete(StoredFile).where(StoredFile.path.in_(gone)))
            await session.commit()
        for key in changed:
            self.known[key] = found[key][1]
        for key in gone:
            self.known.pop(key, None)
        return len(changed), len(gone)

    async def loop(self, every: float = SYNC_EVERY, sleep: Callable[[float], object] = asyncio.sleep) -> None:
        while True:
            await sleep(every)  # type: ignore[misc]
            try:
                await self.sync()
            except Exception:
                log.exception("Сохранение файлов в базу")


def _write(target: Path, data: bytes, mtime: float) -> None:
    import os

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    os.utime(target, (mtime, mtime))
