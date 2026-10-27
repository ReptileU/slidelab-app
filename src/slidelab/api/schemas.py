"""Ответы API. Тексты каталога отдаются уже на языке клиента."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from slidelab.core.enums import (
    Deadline,
    Design,
    Lang,
    OrderStatus,
    PaidFrom,
    PlanCode,
    SlideTier,
)
from slidelab.core.schemas.order import RevisionText


class PackageOut(BaseModel):
    plan: PlanCode
    left: int
    total: int
    expires_at: datetime


class MeOut(BaseModel):
    id: int
    first_name: str
    username: str | None
    photo_url: str | None
    lang: Lang | None
    first_order_price: int | None  # есть только у нового клиента
    package: PackageOut | None
    active_orders: int


class LangIn(BaseModel):
    lang: Lang


class PricesOut(BaseModel):
    s10: int
    s20: int
    s30: int
    urgent_pct: int
    extra_text: int
    extra_notes: int
    first_order_s10: int
    uzs_per_star: int


class PlanOut(BaseModel):
    code: PlanCode
    count: int
    price: int
    days: int
    notes_free: bool
    priority: bool
    max_parallel: int | None


class StyleOut(BaseModel):
    key: str
    name: str
    hint: str
    tags: list[str]
    images: list[str]
    is_real_work: bool


class WorkOut(BaseModel):
    image: str
    title: str
    style: str


class FaqOut(BaseModel):
    q: str
    a: str


class CatalogOut(BaseModel):
    prices: PricesOut
    plans: list[PlanOut]
    styles: list[StyleOut]
    works: list[WorkOut]
    faq: list[FaqOut]
    bot_username: str
    channel_username: str


class QuoteIn(BaseModel):
    slides: SlideTier
    deadline: Deadline
    extra_text: bool = False
    extra_notes: bool = False


class QuoteOut(BaseModel):
    price: int
    paid_from: PaidFrom
    package_cost: int
    package_left_after: int | None
    first_order_discount: bool


class EventOut(BaseModel):
    status: OrderStatus
    at: datetime


class OrderOut(BaseModel):
    id: int
    topic: str
    slides: SlideTier
    deadline: Deadline
    pres_lang: Lang
    design: Design
    style_key: str | None
    status: OrderStatus
    price: int
    paid_from: PaidFrom
    package_cost: int
    revisions_left: int
    has_cover: bool
    has_result: bool
    created_at: datetime
    events: list[EventOut] = Field(default_factory=list)


class InvoiceIn(BaseModel):
    provider: Literal["stars", "card"]


class InvoiceOut(BaseModel):
    provider: Literal["stars", "card"]
    url: str | None = None  # ссылка для Telegram.WebApp.openInvoice
    amount: int
    currency: str
    # Для перевода: реквизиты отправлены в чат, чек клиент пришлёт туда же


class RevisionIn(BaseModel):
    text: RevisionText


class SupportIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ReviewIn(BaseModel):
    order_id: int | None = None
    stars: int = Field(ge=1, le=5)
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class OkOut(BaseModel):
    ok: bool = True
