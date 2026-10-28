from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from slidelab.core.enums import (
    AttachmentKind,
    Deadline,
    Design,
    Lang,
    OrderSource,
    OrderStatus,
    PaidFrom,
    SlideTier,
    Stage,
)
from slidelab.core.models.base import Base, CreatedAtMixin, str_enum, utcnow

# Ограничения длины — как в форме текущего index.html
TOPIC_MAX = 300
TEMPLATE_URL_MAX = 500
CONTACT_MAX = 60
COMMENT_MAX = 400
SOURCES_MAX = 1500
REVISION_MAX = 1500
FREE_REVISIONS = 2


class Order(CreatedAtMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    topic: Mapped[str] = mapped_column(String(TOPIC_MAX))
    slides: Mapped[SlideTier] = mapped_column(str_enum(SlideTier))
    deadline: Mapped[Deadline] = mapped_column(str_enum(Deadline))
    pres_lang: Mapped[Lang] = mapped_column(str_enum(Lang))
    design: Mapped[Design] = mapped_column(str_enum(Design))
    style_id: Mapped[int | None] = mapped_column(ForeignKey("showcase_styles.id"))
    template_url: Mapped[str | None] = mapped_column(String(TEMPLATE_URL_MAX))
    extra_text: Mapped[bool] = mapped_column(default=False)
    extra_notes: Mapped[bool] = mapped_column(default=False)
    contact: Mapped[str | None] = mapped_column(String(CONTACT_MAX))
    comment: Mapped[str | None] = mapped_column(String(COMMENT_MAX))
    sources: Mapped[str | None] = mapped_column(String(SOURCES_MAX))
    has_source_files: Mapped[bool] = mapped_column(default=False)
    need_humor: Mapped[bool] = mapped_column(default=False)  # «С юмором»: мемы по теме
    source: Mapped[OrderSource] = mapped_column(str_enum(OrderSource), default=OrderSource.CHAT)
    ui_lang: Mapped[Lang] = mapped_column(str_enum(Lang), default=Lang.RU)  # язык общения с клиентом

    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.NEW, index=True)
    # Сумма к оплате деньгами. Для заказа из пакета — только доплата (срочность, текст, конспект).
    price: Mapped[int]
    paid_from: Mapped[PaidFrom] = mapped_column(str_enum(PaidFrom), default=PaidFrom.CASH)
    # Сколько презентаций спишется из пакета (21–30 слайдов — 2)
    package_cost: Mapped[int] = mapped_column(default=0)
    revisions_left: Mapped[int] = mapped_column(default=FREE_REVISIONS)
    # Оплачено целиком: деньгами, звёздами или пакетом без доплаты. Платить можно и до обложки.
    is_paid: Mapped[bool] = mapped_column(default=False)

    # Конвейер Claude (папка orders/<id>/)
    stage: Mapped[Stage | None] = mapped_column(str_enum(Stage), index=True)
    stage_at: Mapped[datetime | None]
    alerted: Mapped[str | None] = mapped_column(String(64))  # о чём уже предупредили админа
    alerted_at: Mapped[datetime | None]
    no_alert: Mapped[bool] = mapped_column(default=False)

    # Выдача готового: папка в orders/<id>/, имена файлов, ссылки (gslides, canva, view)
    deliver_dir: Mapped[str | None] = mapped_column(String(128))
    deliver_files: Mapped[list[Any] | None]
    deliver_links: Mapped[dict[str, Any] | None]
    delivered: Mapped[bool] = mapped_column(default=False)
    result_link: Mapped[str | None] = mapped_column(String(TEMPLATE_URL_MAX))  # ссылка, присланная админом
    hidden: Mapped[bool] = mapped_column(default=False)  # клиент убрал из «Моих работ»

    # Зачёт заказа в пакет: несколько дней после сдачи можно купить пакет со скидкой на цену заказа
    credit_until: Mapped[datetime | None]
    credit_used: Mapped[bool] = mapped_column(default=False)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # карточка заказа в теме клиента у менеджеров — редактируется при смене статуса
    managers_message_id: Mapped[int | None]

    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, server_default=func.now())

    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="order", order_by="OrderEvent.id", cascade="all, delete-orphan"
    )


class OrderEvent(CreatedAtMixin, Base):
    """История смены статусов: кто, когда, из какого в какой."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[OrderStatus | None] = mapped_column(str_enum(OrderStatus))
    to_status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="events")


class Attachment(CreatedAtMixin, Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AttachmentKind] = mapped_column(str_enum(AttachmentKind))
    tg_file_id: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(TEMPLATE_URL_MAX))
    file_name: Mapped[str | None] = mapped_column(String(256))
    mime_type: Mapped[str | None] = mapped_column(String(128))


class Revision(CreatedAtMixin, Base):
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(REVISION_MAX))
    is_paid: Mapped[bool] = mapped_column(default=False)  # сверх двух бесплатных
