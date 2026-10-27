"""Счёт из Mini App: звёзды — ссылка для openInvoice, перевод — реквизиты и кнопка «Я оплатил» в чат."""

from aiogram import Bot
from aiogram.types import LabeledPrice

from slidelab.api.schemas import InvoiceOut
from slidelab.core.enums import PlanCode
from slidelab.core.errors import InvalidTransitionError
from slidelab.core.models import Order, Payment, User
from slidelab.core.services.packages import Credit
from slidelab.telegram.notifier import Notifier


def ensure_stars(notifier: Notifier) -> None:
    if not notifier.settings.stars:
        raise InvalidTransitionError("Оплата звёздами сейчас выключена — выберите перевод на карту")


async def stars_invoice(payment: Payment, title: str, description: str, *, bot: Bot) -> InvoiceOut:
    url = await bot.create_invoice_link(
        title=title[:32],
        description=description[:255],
        payload=f"pay:{payment.id}",
        currency=payment.currency,
        prices=[LabeledPrice(label=title[:32], amount=payment.amount)],
    )
    return InvoiceOut(provider="stars", url=url, amount=payment.amount, currency=payment.currency)


async def card_in_chat(
    notifier: Notifier,
    user: User,
    amount: int,
    *,
    order: Order | None = None,
    plan: PlanCode | None = None,
    credit: Credit | None = None,
) -> InvoiceOut:
    """Реквизиты — в чат с ботом: там клиент нажмёт «Я оплатил» и пришлёт чек."""
    await notifier.send_pay(user, amount=amount, order=order, plan=plan, credit=credit)
    return InvoiceOut(provider="card", amount=amount, currency="UZS")
