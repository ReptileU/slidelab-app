from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Integer, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# BIGINT в PostgreSQL; в SQLite автоинкремент работает только у INTEGER (нужно для тестов)
BigInt = BigInteger().with_variant(Integer(), "sqlite")
JsonType = JSON().with_variant(JSONB(), "postgresql")

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def str_enum(enum: type[StrEnum]) -> Enum:
    """Enum хранится строкой (VARCHAR), а не нативным типом — новые значения без миграции типа."""
    return Enum(enum, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite отдаёт даты без часового пояса — считаем их UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        int: BigInt,
        datetime: DateTime(timezone=True),
        dict[str, Any]: JsonType,
        list[Any]: JsonType,
    }


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
