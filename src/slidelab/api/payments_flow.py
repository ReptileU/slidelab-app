"""Счёт из Mini App: звёзды — ссылка для openInvoice, перевод — реквизиты и кнопка «Я оплатил» в чат."""

import base64
import binascii
import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, LabeledPrice

from slidelab.api.schemas import InvoiceOut, PayCardOut
from slidelab.core.enums import PlanCode
from slidelab.core.errors import DomainError, InvalidTransitionError
from slidelab.core.i18n import money
from slidelab.core.models import Order, Payment, User
from slidelab.core.services.packages import Credit
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.notifier import Notifier

log = logging.getLogger(__name__)
MAX_RECEIPT = 3_000_000


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


def card_in_app(notifier: Notifier, amount: int) -> InvoiceOut:
    """Реквизиты — прямо в приложение: номера копируются там же, чек приходит на /receipt."""
    cards = notifier.settings.pay_cards
    if not cards:
        raise InvalidTransitionError("Перевод на карту сейчас недоступен — выберите другой способ")
    return InvoiceOut(
        provider="card",
        amount=amount,
        currency="UZS",
        cards=[PayCardOut(label=label, number=number) for label, number in cards],
        name=notifier.settings.pay_name,
    )


def decode_image(raw: str) -> tuple[bytes, str]:
    """data:image/...;base64,... → байты и расширение. Только JPEG/PNG/WebP разумного размера."""
    data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
    try:
        blob = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise DomainError("Не получилось прочитать скриншот — попробуйте другой файл") from None
    if blob[:4] == b"\x89PNG":
        ext = "png"
    elif blob[:2] == b"\xff\xd8":
        ext = "jpg"
    elif blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        ext = "webp"
    else:
        raise DomainError("Пришлите скриншот картинкой (JPG или PNG)")
    if len(blob) > MAX_RECEIPT:
        raise DomainError("Скриншот слишком большой — до 3 МБ")
    return blob, ext


async def receipt_to_staff(notifier: Notifier, user: User, payment: Payment, what: str, blob: bytes, ext: str) -> None:
    """Чек из приложения — владельцу, как чек из чата: подпись, скриншот и кнопки «Деньги пришли?»."""
    await notifier.staff(
        f"🧾 <b>Чек из приложения: {what}</b> · {money(payment.amount)} сум\n"
        f"{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>\n"
        "Проверьте поступление на карту 👇",
        user=user,
    )
    chat_id = notifier.settings.staff_chat_id
    if chat_id is not None:
        try:
            thread = await notifier.topic(user)
            file = BufferedInputFile(blob, filename=f"check_{payment.id}.{ext}")
            try:
                await notifier.bot.send_photo(chat_id, file, message_thread_id=thread)
            except TelegramAPIError:  # необычный формат или размер — отправим файлом
                await notifier.bot.send_document(chat_id, file, message_thread_id=thread)
        except TelegramAPIError as e:
            log.error("Не удалось переслать чек: %s", e)
    await notifier.staff("Деньги пришли?", kb.staff_receipt(payment.id), user=user)
