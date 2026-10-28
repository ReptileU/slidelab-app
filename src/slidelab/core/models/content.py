from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.enums import MessageDirection
from slidelab.core.models.base import Base, CreatedAtMixin, str_enum

# Тексты на трёх языках лежат в JSON: {"ru": {...}, "uz": {...}, "en": {...}}


class ShowcaseStyle(Base):
    __tablename__ = "showcase_styles"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    tags: Mapped[list[Any]]  # study / business / dark / light
    images: Mapped[list[Any]]  # обложка первой, затем слайды
    is_real_work: Mapped[bool] = mapped_column(default=False)  # наша работа, а не пример стиля
    texts: Mapped[dict[str, Any]]  # {"ru": {"name": "...", "hint": "..."}}
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class PortfolioWork(Base):
    __tablename__ = "portfolio_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    image: Mapped[str] = mapped_column(String(256))
    texts: Mapped[dict[str, Any]]  # {"ru": {"title": "...", "subtitle": "..."}}
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class FaqItem(Base):
    __tablename__ = "faq_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    texts: Mapped[dict[str, Any]]  # {"ru": {"q": "...", "a": "..."}}
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Review(CreatedAtMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    stars: Mapped[int]
    text: Mapped[str | None] = mapped_column(Text)


class SupportMessage(CreatedAtMixin, Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(str_enum(MessageDirection))
    text: Mapped[str] = mapped_column(Text)
    # id сообщения в теме менеджеров — чтобы ответ «reply» нашёл клиента
    managers_message_id: Mapped[int | None]
