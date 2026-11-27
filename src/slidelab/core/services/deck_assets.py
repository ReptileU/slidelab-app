"""Картинки конструктора презентаций: сжатие и хранение вне базы.

В базе (deck_assets) — только ключ хранилища и размеры. Сейчас файлы хранит Telegram: бот отправляет картинку
документом в закрытый канал и запоминает file_id (ключ «tg:<file_id>»). Хранилище подменяемое (AssetStore):
когда появится Cloudflare R2, достаточно добавить R2Store с ключами «r2:<путь>» — старые «tg:» продолжат читаться.
"""

import io
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from aiogram import Bot
from aiogram.types import BufferedInputFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import DeckAssetKind
from slidelab.core.errors import DomainError, NotFoundError
from slidelab.core.models import Deck, DeckAsset

MAX_UPLOAD = 12 * 1024 * 1024  # байт на входе (до сжатия)
MAX_SIDE = 2000  # px по длинной стороне после сжатия
MAX_PIXELS = 50_000_000  # защита от «картинок-бомб»
MAX_ASSETS = 40  # на презентацию
QUALITY = 85
CACHE_BYTES = 64 * 1024 * 1024  # сжатые картинки в памяти сервера, чтобы не ходить в Telegram на каждый показ


class AssetError(DomainError):
    code = "asset_invalid"


class AssetLimitError(DomainError):
    code = "asset_limit"


class StorageUnavailableError(DomainError):
    code = "storage_unavailable"


@dataclass(frozen=True, slots=True)
class Processed:
    data: bytes
    width: int
    height: int


def process_image(blob: bytes) -> Processed:
    """Любая JPEG/PNG/WebP → WebP не больше MAX_SIDE, с учётом поворота из EXIF, прозрачность сохраняется."""
    if len(blob) > MAX_UPLOAD:
        raise AssetError("Картинка слишком большая — до 12 МБ")
    try:
        with Image.open(io.BytesIO(blob)) as probe:
            fmt = probe.format
            w, h = probe.size
        if fmt not in ("JPEG", "PNG", "WEBP"):
            raise AssetError("Нужна картинка JPG, PNG или WebP")
        if w * h > MAX_PIXELS:
            raise AssetError("Слишком большое разрешение")
        with Image.open(io.BytesIO(blob)) as img:
            img.load()
            out = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AssetError("Не получилось открыть картинку — попробуйте другой файл") from None
    alpha = out.mode in ("RGBA", "LA", "PA") or (out.mode == "P" and "transparency" in out.info)
    out = out.convert("RGBA" if alpha else "RGB")
    out.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "WEBP", quality=QUALITY, method=4)
    return Processed(buf.getvalue(), out.width, out.height)


class AssetStore(Protocol):
    async def put(self, data: bytes, filename: str) -> str: ...
    async def get(self, key: str) -> bytes: ...


class TelegramStore:
    """Файлы — документами в закрытом канале. Документ, а не фото: Telegram не пережимает его."""

    def __init__(self, bot: Bot, chat_id: int | None) -> None:
        self.bot = bot
        self.chat_id = chat_id

    async def put(self, data: bytes, filename: str) -> str:
        if self.chat_id is None:
            raise StorageUnavailableError("Не задан ASSETS_CHAT_ID — некуда сохранить картинку")
        msg = await self.bot.send_document(
            self.chat_id, BufferedInputFile(data, filename=filename), disable_notification=True
        )
        if msg.document is None:
            raise StorageUnavailableError("Telegram не вернул файл")
        return f"tg:{msg.document.file_id}"

    async def get(self, key: str) -> bytes:
        prefix, _, file_id = key.partition(":")
        if prefix != "tg" or not file_id:
            raise NotFoundError("Файл в другом хранилище")
        file = await self.bot.get_file(file_id)
        if file.file_path is None:
            raise NotFoundError("Файл пропал из Telegram")
        buf = io.BytesIO()
        await self.bot.download_file(file.file_path, destination=buf)
        return buf.getvalue()


class _Cache:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.size = 0
        self.items: OrderedDict[str, bytes] = OrderedDict()

    def get(self, key: str) -> bytes | None:
        data = self.items.get(key)
        if data is not None:
            self.items.move_to_end(key)
        return data

    def put(self, key: str, data: bytes) -> None:
        if key in self.items or len(data) > self.limit:
            return
        self.items[key] = data
        self.size += len(data)
        while self.size > self.limit:
            _, old = self.items.popitem(last=False)
            self.size -= len(old)


CACHE = _Cache(CACHE_BYTES)


class DeckAssetService:
    def __init__(self, session: AsyncSession, store: AssetStore) -> None:
        self.session = session
        self.store = store

    async def add(self, deck: Deck, kind: DeckAssetKind, blob: bytes) -> DeckAsset:
        count = await self.session.scalar(select(func.count(DeckAsset.id)).where(DeckAsset.deck_id == deck.id))
        if (count or 0) >= MAX_ASSETS:
            raise AssetLimitError(f"Не больше {MAX_ASSETS} картинок в презентации")
        img = process_image(blob)
        key = await self.store.put(img.data, f"deck{deck.id}_{kind.value}.webp")
        asset = DeckAsset(
            deck_id=deck.id, kind=kind, storage_key=key, width=img.width, height=img.height, bytes=len(img.data)
        )
        self.session.add(asset)
        await self.session.flush()
        CACHE.put(key, img.data)
        return asset

    async def list_for(self, deck: Deck) -> list[DeckAsset]:
        rows = await self.session.scalars(select(DeckAsset).where(DeckAsset.deck_id == deck.id).order_by(DeckAsset.id))
        return list(rows)

    async def get(self, deck: Deck, asset_id: int) -> DeckAsset:
        asset = await self.session.get(DeckAsset, asset_id)
        if asset is None or asset.deck_id != deck.id:
            raise NotFoundError("Нет такой картинки")
        return asset

    async def read(self, asset: DeckAsset) -> bytes:
        data = CACHE.get(asset.storage_key)
        if data is None:
            data = await self.store.get(asset.storage_key)
            CACHE.put(asset.storage_key, data)
        return data

    async def delete(self, deck: Deck, asset_id: int) -> None:
        """Запись удаляется; сам файл в канале остаётся (Telegram не даёт боту чистить старое массово)."""
        asset = await self.get(deck, asset_id)
        await self.session.delete(asset)
        await self.session.flush()
