from aiogram.filters.callback_data import CallbackData


class LangCb(CallbackData, prefix="lang"):
    code: str


class FormCb(CallbackData, prefix="f"):
    """Анкета заказа: field — slides / deadline / plang / design / extra / files / action."""

    field: str
    value: str


class QuickCb(CallbackData, prefix="q"):
    """Быстрый заказ по пересланному файлу: field — slides / deadline."""

    field: str
    value: str


class OrderCb(CallbackData, prefix="o"):
    """Действия клиента с заказом."""

    action: str  # show, pay, cover_ok, cover_change, revise, send_revision, good, files, hide
    order_id: int


class FmtCb(CallbackData, prefix="fmt"):
    order_id: int
    fmt: str  # pptx, pdf, png, gslides, canva, all


class PayCb(CallbackData, prefix="pay"):
    """Оплата: kind — order / plan; ref — номер заказа или код тарифа; credit — засчитываемый заказ."""

    action: str  # card (я оплатил картой), stars (счёт сообщением, если ссылка не создалась)
    kind: str
    ref: str
    credit: int = 0


class PlanCb(CallbackData, prefix="p"):
    code: str
    credit: int = 0  # засчитать сданный заказ


class RateCb(CallbackData, prefix="r"):
    order_id: int
    stars: int


class MgrCb(CallbackData, prefix="m"):
    """Кнопки владельца и менеджеров."""

    action: str
    order_id: int = 0
    payment_id: int = 0
