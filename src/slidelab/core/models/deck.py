"""Конструктор презентаций: презентация целиком — один JSON, картинки — только ссылки на хранилище."""

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.enums import CreditReason, DeckAssetKind, DeckStatus, Lang
from slidelab.core.models.base import Base, CreatedAtMixin, str_enum, utcnow

DECK_TITLE_MAX = 120


class Deck(CreatedAtMixin, Base):
    __tablename__ = "decks"
    __table_args__ = (Index("ix_decks_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(DECK_TITLE_MAX))
    lang: Mapped[Lang] = mapped_column(str_enum(Lang))
    status: Mapped[DeckStatus] = mapped_column(str_enum(DeckStatus), default=DeckStatus.DRAFT)
    # растёт на каждом сохранении: правка с устаревшей версией (вторая вкладка, другой телефон) отклоняется
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    body: Mapped[dict[str, Any]]  # тема и слайды, схема — services/decks.py
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class DeckAsset(CreatedAtMixin, Base):
    """Файл презентации. Байтов в базе нет — только ключ в хранилище (R2 или Telegram file_id)."""

    __tablename__ = "deck_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[DeckAssetKind] = mapped_column(str_enum(DeckAssetKind))
    storage_key: Mapped[str] = mapped_column(String(256))
    width: Mapped[int]
    height: Mapped[int]
    bytes: Mapped[int]


class CreditsLedger(CreatedAtMixin, Base):
    """Каждое движение кредитов отдельной строкой — баланс всегда можно проверить."""

    __tablename__ = "credits_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int]
    reason: Mapped[CreditReason] = mapped_column(str_enum(CreditReason))
    action: Mapped[str | None] = mapped_column(String(32))  # на что потратил: draft, suggest…
    deck_id: Mapped[int | None] = mapped_column(ForeignKey("decks.id", ondelete="SET NULL"))
