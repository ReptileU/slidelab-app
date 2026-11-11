"""Карточки SlideLab: заказ и статус заказа. HTML лежит рядом, тексты — здесь (на трёх языках)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from slidelab.core.enums import Deadline, Lang, OrderStatus, SlideTier, Stage
from slidelab.core.i18n import money
from slidelab.core.models import Order
from slidelab.core.services import pricing

from .api import check_data, check_html

HERE = Path(__file__).parent
LANGS = [Lang.RU, Lang.UZ, Lang.EN]
TIERS = [SlideTier.S10, SlideTier.S20, SlideTier.S30]
DEADLINES = [Deadline.URGENT, Deadline.NORMAL, Deadline.RELAXED]

ORDER_TEXTS: dict[Lang, dict[str, object]] = {
    Lang.RU: {
        "title": "Новая презентация",
        "vol": "Объём",
        "vols": ["До 15", "16–20", "21–30"],
        "dl": "Срок",
        "dls": ["Срочно", "Обычно", "Не спешу"],
        "lng": "Язык презентации",
        "lngs": ["Русский", "O‘zbek", "English"],
        "ext": "Дополнительно",
        "xs": ["Текст под ключ +5 000", "Конспект +5 000", "С юмором"],
        "order": "Заказать",
        "sum": "сум",
        "pack": "из пакета",
        "wait": "Секунду…",
        "err": "Не получилось — нажмите ещё раз",
        "ask": "✍️ Напишите тему презентации сообщением ниже",
        "done": "✅ Заказ # принят — статус ниже",
        "caption": "Обложка — бесплатно. Платите, только если понравится стиль.",
    },
    Lang.UZ: {
        "title": "Yangi taqdimot",
        "vol": "Hajm",
        "vols": ["15 gacha", "16–20", "21–30"],
        "dl": "Muddat",
        "dls": ["Shoshilinch", "Odatiy", "Shoshmayman"],
        "lng": "Taqdimot tili",
        "lngs": ["Русский", "O‘zbek", "English"],
        "ext": "Qo‘shimcha",
        "xs": ["Tayyor matn +5 000", "Konspekt +5 000", "Hazil bilan"],
        "order": "Buyurtma",
        "sum": "so‘m",
        "pack": "paketdan",
        "wait": "Bir soniya…",
        "err": "Bo‘lmadi — yana bosing",
        "ask": "✍️ Taqdimot mavzusini pastda xabar qilib yozing",
        "done": "✅ # buyurtma qabul qilindi — holati pastda",
        "caption": "Muqova — bepul. Uslub yoqsagina to‘laysiz.",
    },
    Lang.EN: {
        "title": "New presentation",
        "vol": "Size",
        "vols": ["Up to 15", "16–20", "21–30"],
        "dl": "Deadline",
        "dls": ["Urgent", "Normal", "No rush"],
        "lng": "Presentation language",
        "lngs": ["Русский", "O‘zbek", "English"],
        "ext": "Extras",
        "xs": ["Full text +5 000", "Speaker notes +5 000", "With humor"],
        "order": "Order",
        "sum": "UZS",
        "pack": "from package",
        "wait": "One sec…",
        "err": "Didn’t work — tap again",
        "ask": "✍️ Send the presentation topic as a message below",
        "done": "✅ Order # placed — status below",
        "caption": "The cover is free. Pay only if you like the style.",
    },
}

STATUS_TEXTS: dict[Lang, dict[str, object]] = {
    Lang.RU: {"no": "Заказ #", "steps": ["Принят", "Обложка", "В работе", "Готово"], "view": "Посмотреть презентацию"},
    Lang.UZ: {"no": "Buyurtma #", "steps": ["Qabul", "Muqova", "Ishda", "Tayyor"], "view": "Taqdimotni ko‘rish"},
    Lang.EN: {"no": "Order #", "steps": ["Placed", "Cover", "In work", "Done"], "view": "View the presentation"},
}

# (шаг шкалы, заголовок, пояснение) по статусу/стадии заказа
HINTS: dict[Lang, dict[str, tuple[str, str]]] = {
    Lang.RU: {
        "cover": ("🎨 Делаем бесплатную обложку", "Пришлём её в этот чат — посмотрите стиль"),
        "cover_sent": ("👀 Обложка у вас в чате", "Нравится — жмите «Беру», нет — попросите другую"),
        "pay": ("💳 Ждём оплату", "После оплаты сразу начнём всю презентацию"),
        "work": ("⚙️ Делаем презентацию", "Пришлём файлы сюда, как только будут готовы"),
        "revision": ("✏️ Вносим правки", "Пришлём обновлённые файлы в этот чат"),
        "done": ("✅ Готово", "Файлы в чате. Спасибо, что выбрали SlideLab!"),
        "cancelled": ("Заказ отменён", "Если это ошибка — напишите нам"),
    },
    Lang.UZ: {
        "cover": ("🎨 Bepul muqova tayyorlanmoqda", "Shu chatga yuboramiz — uslubni ko‘ring"),
        "cover_sent": ("👀 Muqova chatda", "Yoqsa — «Olaman», yo‘q — boshqasini so‘rang"),
        "pay": ("💳 To‘lov kutilmoqda", "To‘lovdan so‘ng darhol boshlaymiz"),
        "work": ("⚙️ Taqdimot tayyorlanmoqda", "Tayyor bo‘lishi bilan fayllarni yuboramiz"),
        "revision": ("✏️ Tuzatishlar kiritilmoqda", "Yangilangan fayllarni shu chatga yuboramiz"),
        "done": ("✅ Tayyor", "Fayllar chatda. SlideLab’ni tanlaganingiz uchun rahmat!"),
        "cancelled": ("Buyurtma bekor qilindi", "Xato bo‘lsa — bizga yozing"),
    },
    Lang.EN: {
        "cover": ("🎨 Making your free cover", "We’ll send it to this chat — check the style"),
        "cover_sent": ("👀 The cover is in the chat", "Like it — tap “Take it”, or ask for another"),
        "pay": ("💳 Waiting for payment", "We start the full deck right after payment"),
        "work": ("⚙️ Making the presentation", "We’ll send the files here as soon as they’re ready"),
        "revision": ("✏️ Making your edits", "We’ll send the updated files to this chat"),
        "done": ("✅ Done", "Files are in the chat. Thanks for choosing SlideLab!"),
        "cancelled": ("Order cancelled", "If this is a mistake — message us"),
    },
}


def lang_or_ru(lang: Lang | str | None) -> Lang:
    try:
        return Lang(lang) if lang else Lang.RU
    except ValueError:
        return Lang.RU


@cache
def _template(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def order_html(lang: Lang) -> str:
    texts = dict(ORDER_TEXTS[lang])
    texts.pop("caption")
    texts["lang"] = LANGS.index(lang)
    return check_html(_template("order.html").replace("__T__", json.dumps(texts, ensure_ascii=False)))


def status_html(lang: Lang) -> str:
    return check_html(_template("status.html").replace("__T__", json.dumps(STATUS_TEXTS[lang], ensure_ascii=False)))


def price_table(
    rules: pricing.PriceRules, *, first_order: bool, package: pricing.PackageBalance | None
) -> tuple[list[int], list[int]]:
    """Цены всех 36 сочетаний (объём × срок × текст × конспект) — карточка считает итог сама, без запросов.

    -1 — сочетание недоступно (срочно 21–30). Второй список — старая цена для зачёркивания (0 — нет скидки).
    """
    prices: list[int] = []
    olds: list[int] = []
    for tier in TIERS:
        for dl in DEADLINES:
            for text in (False, True):
                for notes in (False, True):
                    req = pricing.QuoteRequest(slides=tier, deadline=dl, extra_text=text, extra_notes=notes)
                    try:
                        q = pricing.quote(req, rules, first_order=first_order, package=package)
                    except pricing.PricingError:
                        prices.append(-1)
                        olds.append(0)
                        continue
                    prices.append(q.price)
                    full = pricing.quote(req, rules, first_order=False, package=package).price
                    olds.append(full if q.first_order_discount and full > q.price else 0)
    return prices, olds


def order_state(prices: list[int], olds: list[int], st: int = 0, order_id: int | None = None) -> str:
    data: dict[str, object] = {"q": prices, "o": olds, "st": st}
    if order_id:
        data["id"] = order_id
    return check_data(json.dumps(data, separators=(",", ":")))


def parse_order_request(data: str) -> tuple[SlideTier, Deadline, Lang, bool, bool, bool] | None:
    """'o:' + объём + срок + язык + флаги (1 текст, 2 конспект, 4 юмор), например 'o:1103'."""
    if not data.startswith("o:") or len(data) != 6 or not data[2:].isdigit():
        return None
    s, d, lg, flags = (int(c) for c in data[2:])
    if s > 2 or d > 2 or lg > 2 or flags > 7:
        return None
    tier, deadline = TIERS[s], DEADLINES[d]
    if tier is SlideTier.S30 and deadline is Deadline.URGENT:
        deadline = Deadline.NORMAL
    return tier, deadline, LANGS[lg], bool(flags & 1), bool(flags & 2), bool(flags & 4)


def status_key(order: Order) -> tuple[int, str]:
    """(шаг шкалы 0–3 или -1, ключ подсказки) — из статуса и стадии заказа."""
    st = order.status
    if st is OrderStatus.CANCELLED:
        return -1, "cancelled"
    if st is OrderStatus.DONE:
        return 3, "done"
    if st is OrderStatus.REVISION:
        return 2, "revision"
    if st is OrderStatus.WORK:
        return 2, "work"
    if st is OrderStatus.AWAITING_PAYMENT:
        return 1, "pay"
    if st is OrderStatus.COVER or order.stage in (Stage.COVER_SENT, Stage.COVER_OK):
        return 1, "cover_sent"
    return 0, "cover"


def status_state(order: Order, lang: Lang, bot_username: str | None = None) -> str:
    step, key = status_key(order)
    title, sub = HINTS[lang][key]
    topic = order.topic if len(order.topic) <= 60 else order.topic[:59] + "…"
    data: dict[str, object] = {"n": order.id, "t": topic, "s": step, "h": title, "d": sub}
    if order.price:
        data["p"] = f"{money(order.price)} {ORDER_TEXTS[lang]['sum']}"
    has_deck = any(str(n).lower().endswith(".pdf") for n in (order.deliver_files or []))
    if bot_username and has_deck and step >= 2:
        data["l"] = f"https://t.me/{bot_username}?startapp=order_{order.id}"  # просмотр слайдов в приложении
    return check_data(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def status_caption(order: Order, lang: Lang) -> str:
    _, key = status_key(order)
    return f"{STATUS_TEXTS[lang]['no']}".replace("#", f"#{order.id}") + f" — {HINTS[lang][key][0]}"


# --- оплата переводом на карту ----------------------------------------------------------

PAY_TEXTS: dict[Lang, dict[str, str]] = {
    Lang.RU: {
        "pay": "Оплата",
        "cards": "Переведите на карту · номер копируется касанием",
        "copy": "копировать",
        "copied": "✓ скопировано",
        "to": "Получатель:",
        "paid": "Я оплатил",
        "wait": "Секунду…",
        "err": "Не получилось — нажмите ещё раз",
        "s1": "📎 Пришлите скриншот оплаты сюда в чат",
        "s2": "✅ Чек получен — проверяем поступление",
        "s3": "✅ Оплата подтверждена. Спасибо!",
        "caption": "После перевода нажмите «Я оплатил» и пришлите скриншот.",
    },
    Lang.UZ: {
        "pay": "To‘lov",
        "cards": "Kartaga o‘tkazing · raqam bosilganda nusxalanadi",
        "copy": "nusxalash",
        "copied": "✓ nusxalandi",
        "to": "Qabul qiluvchi:",
        "paid": "To‘ladim",
        "wait": "Bir soniya…",
        "err": "Bo‘lmadi — yana bosing",
        "s1": "📎 To‘lov skrinshotini shu chatga yuboring",
        "s2": "✅ Chek qabul qilindi — tushumni tekshiryapmiz",
        "s3": "✅ To‘lov tasdiqlandi. Rahmat!",
        "caption": "O‘tkazmadan so‘ng «To‘ladim» ni bosing va skrinshot yuboring.",
    },
    Lang.EN: {
        "pay": "Payment",
        "cards": "Transfer to a card · tap a number to copy",
        "copy": "copy",
        "copied": "✓ copied",
        "to": "Recipient:",
        "paid": "I’ve paid",
        "wait": "One sec…",
        "err": "Didn’t work — tap again",
        "s1": "📎 Send a screenshot of the payment to this chat",
        "s2": "✅ Receipt received — checking the transfer",
        "s3": "✅ Payment confirmed. Thank you!",
        "caption": "After the transfer, tap “I’ve paid” and send a screenshot.",
    },
}


def pay_html(lang: Lang) -> str:
    texts = {k: v for k, v in PAY_TEXTS[lang].items() if k != "caption"}
    return check_html(_template("pay.html").replace("__T__", json.dumps(texts, ensure_ascii=False)))


def pay_state(data: dict[str, object]) -> str:
    return check_data(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def parse_pay_request(data: str) -> tuple[str, str, int] | None:
    """'p:<order|plan>:<номер или тариф>:<зачтённый заказ>' → (kind, ref, credit)."""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "p" or parts[1] not in ("order", "plan") or not parts[3].isdigit():
        return None
    if not parts[2] or len(parts[2]) > 20 or not parts[2].replace("_", "").isalnum():
        return None
    return parts[1], parts[2], int(parts[3])
