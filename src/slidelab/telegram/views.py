"""Тексты сообщений, собранные из данных: карточка заказа, прайс, пакеты."""

import html
from datetime import datetime

from slidelab.core.enums import Deadline, Design, Lang, OrderSource, OrderStatus, PaidFrom, Stage
from slidelab.core.i18n import money, t
from slidelab.core.models import Order, PackagePlan, PriceRule, User, UserPackage
from slidelab.core.models.base import as_utc

STATUS_RU = {
    OrderStatus.NEW: "Новый",
    OrderStatus.COVER: "Обложка у клиента",
    OrderStatus.AWAITING_PAYMENT: "Ждём оплату",
    OrderStatus.WORK: "В работе",
    OrderStatus.DONE: "Готово",
    OrderStatus.REVISION: "Правки",
    OrderStatus.CANCELLED: "Отменён",
}
STAGE_RU = {
    Stage.COVER_TODO: "Claude делает обложку",
    Stage.COVER_REVIEW: "обложка ждёт вашей проверки",
    Stage.COVER_SENT: "обложка у клиента",
    Stage.COVER_OK: "клиент одобрил обложку, ждём оплату",
    Stage.DECK_TODO: "Claude делает презентацию",
    Stage.DECK_REVIEW: "презентация ждёт вашей проверки",
    Stage.EDIT_TODO: "Claude вносит правки",
    Stage.EDIT_REVIEW: "правки ждут вашей проверки",
    Stage.DONE: "сдано",
}
SOURCE_RU = {OrderSource.CHAT: "анкета в чате", OrderSource.APP: "приложение", OrderSource.FILE: "пересланный файл"}
DEADLINE_RU = {Deadline.URGENT: "срочно", Deadline.NORMAL: "обычно", Deadline.RELAXED: "не спешит"}
LANG_RU = {Lang.RU: "русский", Lang.UZ: "узбекский", Lang.EN: "английский"}


def client_name(user: User) -> str:
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or "Клиент"
    return f"{name} @{user.username}" if user.username else name


def date_short(value: object) -> str:
    return as_utc(value).strftime("%d.%m") if isinstance(value, datetime) else ""


def staff_card(order: Order, user: User, style_name: str | None = None) -> str:
    """Карточка заказа для владельца. Строка «ID:» нужна, чтобы ответ реплаем ушёл клиенту."""
    e = html.escape
    lines = [
        f"<b>Заказ #{order.id}</b> · {STATUS_RU[order.status]}",
        f"{e(client_name(user))} · ID: <code>{user.tg_id}</code>",
        f"{SOURCE_RU[order.source]} · общение: {LANG_RU[order.ui_lang]}",
        "",
        f"<b>{e(order.topic)}</b>",
        f"{order.slides.value[1:]} слайдов · {DEADLINE_RU[order.deadline]} · {LANG_RU[order.pres_lang]}",
    ]
    if order.design is Design.OWN:
        lines.append("Дизайн: шаблон клиента" + (f" — {e(order.template_url)}" if order.template_url else ""))
    else:
        lines.append("Дизайн: по теме" + (f" · стиль «{e(style_name)}»" if style_name else ""))
    extras = [
        label
        for label, on in (
            ("текст под ключ", order.extra_text),
            ("конспект", order.extra_notes),
            ("с юмором", order.need_humor),
        )
        if on
    ]
    if extras:
        lines.append("Доп.: " + ", ".join(extras))
    for label, value in (("Контакт", order.contact), ("Пожелания", order.comment), ("Источники", order.sources)):
        if value:
            lines.append(f"{label}: {e(value)}")
    if order.has_source_files:
        lines.append("Клиент пришлёт материалы в чат")
    lines.append("")
    lines.append("Оплата: " + payment_line(order))
    if order.stage:
        lines.append("Сейчас: " + STAGE_RU[order.stage])
    if order.revisions_left < 2:
        lines.append(f"Бесплатных правок осталось: {order.revisions_left}")
    return "\n".join(lines)


def payment_line(order: Order) -> str:
    if order.paid_from is PaidFrom.PACKAGE:
        base = f"из пакета ({order.package_cost} шт)"
        if order.price:
            base += f" + доплата {money(order.price)} сум"
    else:
        base = f"{money(order.price)} сум"
    return base + (" · оплачено ✓" if order.is_paid else " · не оплачено")


def prices(lang: Lang | None, rule: PriceRule) -> str:
    return t(
        lang,
        "prices",
        s10=money(rule.s10),
        s20=money(rule.s20),
        s30=money(rule.s30),
        first=money(rule.first_order_s10),
        urgent=rule.urgent_pct,
        text=money(rule.extra_text),
        notes=money(rule.extra_notes),
    )


def packages(lang: Lang | None, plans: list[PackagePlan], current: UserPackage | None, gift_until: str | None) -> str:
    lines = [t(lang, "packages"), ""]
    lines += [
        t(
            lang,
            "package_line",
            name=t(lang, "plan_" + p.code.value),
            price=money(p.price),
            per=money(p.price // p.count),
            days=p.days,
        )
        for p in plans
    ]
    lines += ["", t(lang, "packages_note")]
    text = "\n".join(lines)
    if current is not None:
        text += t(lang, "my_package", left=current.left, total=current.total, date=date_short(current.expires_at))
    if gift_until:
        text += t(lang, "gift_promo", date=gift_until)
    return text


def client_order_card(lang: Lang | None, order: Order) -> str:
    price = t(lang, "price_from_package") if order.paid_from is PaidFrom.PACKAGE else f"{money(order.price)}"
    return t(
        lang,
        "order_card",
        id=order.id,
        status=t(lang, "st_" + order.status.value),
        topic=html.escape(order.topic),
        slides=t(lang, "slides_" + order.slides.value),
        price=price,
    )
