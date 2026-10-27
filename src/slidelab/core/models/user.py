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
