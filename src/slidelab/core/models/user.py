from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from slidelab.core.enums import Lang
from slidelab.core.models.base import Base, CreatedAtMixin, str_enum


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    lang: Mapped[Lang | None] = mapped_column(str_enum(Lang))  # None — язык ещё не выбран
    phone: Mapped[str | None] = mapped_column(String(32))
    is_manager: Mapped[bool] = mapped_column(default=False)
    # тема клиента в супергруппе менеджеров
    forum_topic_id: Mapped[int | None]
    # Кошелёк в профиле: обложка из фото клиента (имя файла в data/wallet), None — классическая кожа
    wallet_cover: Mapped[str | None] = mapped_column(String(64))
    # Когда последний раз вернули оплату за отмену уже начатой презентации — такой возврат раз в 30 дней
    work_refund_at: Mapped[datetime | None]
    # Баллы за покупки (тратятся на пакет за баллы); сгорают, если до points_expire_at не было новой покупки
    points: Mapped[int] = mapped_column(default=0, server_default="0")
    points_expire_at: Mapped[datetime | None]
    # Кредиты конструктора (действия ИИ). credits_refill_at — когда последний раз пополняли до дневного потолка;
    # None — ещё не получал стартовый подарок
    credits: Mapped[int] = mapped_column(default=0, server_default="0")
    credits_refill_at: Mapped[datetime | None]
    # Скидка в процентах на следующий оплачиваемый заказ (выпала в пакете за баллы)
    discount_pct: Mapped[int | None]
