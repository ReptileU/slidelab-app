"""Клавиатуры. Главное действие — первой кнопкой и на всю ширину, остальное — тише."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from slidelab.core.enums import Deadline, Design, Lang, OrderStatus, PlanCode, SlideTier
from slidelab.core.i18n import TEXTS, money, t
from slidelab.core.models import Order
from slidelab.telegram.callbacks import (
    FmtCb,
    FormCb,
    LangCb,
    MgrCb,
    OrderCb,
    PayCb,
    PlanCb,
    QuickCb,
    RateCb,
)

MENU_KEYS = ("btn_new", "btn_app", "btn_orders", "btn_prices", "btn_examples", "btn_help")


def menu_texts(key: str) -> set[str]:
    """Надпись кнопки меню на всех языках — по ней узнаём нажатие."""
    return {texts[key] for texts in TEXTS.values()}


ALL_MENU_TEXTS: set[str] = set().union(*(menu_texts(k) for k in MENU_KEYS))


def _btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def _rows(*buttons: InlineKeyboardButton) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons])


# --- меню ---------------------------------------------------------------------


def main_menu(lang: Lang, app_url: str | None) -> ReplyKeyboardMarkup:
    """Меню у поля ввода. app_url — старая витрина: только из этой кнопки работает её sendData."""
    first = [[KeyboardButton(text=t(lang, "btn_app"), web_app=WebAppInfo(url=app_url))]] if app_url else []
    return ReplyKeyboardMarkup(
        keyboard=[
            *first,
            [KeyboardButton(text=t(lang, "btn_new")), KeyboardButton(text=t(lang, "btn_orders"))],
            [KeyboardButton(text=t(lang, "btn_prices")), KeyboardButton(text=t(lang, "btn_examples"))],
            [KeyboardButton(text=t(lang, "btn_help"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def open_app(lang: Lang, url: str) -> InlineKeyboardMarkup:
    """Новая Mini App — только кнопкой в сообщении: так Telegram передаёт ей данные пользователя."""
    return _rows(InlineKeyboardButton(text=t(lang, "btn_open_app"), web_app=WebAppInfo(url=url)))


def languages() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Русский", LangCb(code=Lang.RU)),
                _btn("O‘zbekcha", LangCb(code=Lang.UZ)),
                _btn("English", LangCb(code=Lang.EN)),
            ]
        ]
    )


def prices(lang: Lang) -> InlineKeyboardMarkup:
    return _rows(
        _btn(t(lang, "btn_new"), FormCb(field="action", value="start")),
        _btn(t(lang, "btn_packages"), PlanCb(code="list")),
    )


def plans(lang: Lang, items: list[tuple[PlanCode, int]], credit: int = 0) -> InlineKeyboardMarkup:
    return _rows(
        *(
            _btn(
                t(lang, "btn_buy", plan=t(lang, "plan_" + code.value), price=money(price)),
                PlanCb(code=code, credit=credit),
            )
            for code, price in items
        )
    )


def help_menu(lang: Lang) -> InlineKeyboardMarkup:
    return _rows(
        _btn(t(lang, "btn_ask"), FormCb(field="action", value="ask")),
        _btn(t(lang, "btn_language"), FormCb(field="action", value="language")),
    )


# --- анкета -------------------------------------------------------------------


def _cancel(lang: Lang) -> InlineKeyboardButton:
    return _btn(t(lang, "btn_cancel"), FormCb(field="action", value="cancel"))


def slides(
    lang: Lang, tier_prices: dict[SlideTier, int], cb: type[FormCb] | type[QuickCb] = FormCb
) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{t(lang, 'slides_' + s.value)} · {money(tier_prices[s])}", cb(field="slides", value=s))]
        for s in SlideTier
    ]
    if cb is FormCb:
        rows.append([_cancel(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deadlines(lang: Lang, tier: SlideTier, cb: type[FormCb] | type[QuickCb] = FormCb) -> InlineKeyboardMarkup:
    options = [d for d in Deadline if not (d is Deadline.URGENT and tier is SlideTier.S30)]
    rows = [[_btn(t(lang, "dl_" + d.value), cb(field="deadline", value=d))] for d in options]
    if cb is FormCb:
        rows.append([_cancel(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pres_langs(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(t(lang, "plang_" + p.value), FormCb(field="plang", value=p)) for p in Lang],
            [_cancel(lang)],
        ]
    )


def designs(lang: Lang) -> InlineKeyboardMarkup:
    return _rows(
        *(_btn(t(lang, "ds_" + d.value), FormCb(field="design", value=d)) for d in Design),
        _cancel(lang),
    )


def template_later(lang: Lang) -> InlineKeyboardMarkup:
    return _rows(_btn(t(lang, "btn_template_later"), FormCb(field="action", value="no_template")))


def extras(lang: Lang, text: bool, notes: bool, humor: bool) -> InlineKeyboardMarkup:
    def mark(on: bool) -> str:
        return "✓ " if on else ""

    return _rows(
        _btn(mark(text) + t(lang, "x_text"), FormCb(field="extra", value="text")),
        _btn(mark(notes) + t(lang, "x_notes"), FormCb(field="extra", value="notes")),
        _btn(mark(humor) + t(lang, "x_humor"), FormCb(field="extra", value="humor")),
        _btn(t(lang, "btn_next"), FormCb(field="extra", value="next")),
    )


def materials(lang: Lang, has_files: bool) -> InlineKeyboardMarkup:
    key, value = ("btn_done", "done") if has_files else ("btn_skip", "skip")
    return _rows(_btn(t(lang, key), FormCb(field="files", value=value)))


def contact_request(lang: Lang) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirm(lang: Lang) -> InlineKeyboardMarkup:
    return _rows(
        _btn(t(lang, "btn_send"), FormCb(field="action", value="send")),
        _btn(t(lang, "btn_restart"), FormCb(field="action", value="start")),
    )


# --- заказ клиента ------------------------------------------------------------


def cover(lang: Lang, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(t(lang, "btn_cover_ok"), OrderCb(action="cover_ok", order_id=order_id)),
                _btn(t(lang, "btn_cover_change"), OrderCb(action="cover_change", order_id=order_id)),
            ]
        ]
    )


def pay(
    lang: Lang,
    *,
    stars: int | None,
    stars_url: str | None,
    kind: str,
    ref: str,
    cards: bool,
    credit: int = 0,
) -> InlineKeyboardMarkup | None:
    rows = []
    if stars:
        label = t(lang, "btn_pay_stars", stars=stars)
        if stars_url:
            rows.append([InlineKeyboardButton(text=label, url=stars_url)])
        else:
            rows.append([_btn(label, PayCb(action="stars", kind=kind, ref=ref, credit=credit))])
    if cards:
        rows.append([_btn(t(lang, "btn_paid"), PayCb(action="card", kind=kind, ref=ref, credit=credit))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def formats(lang: Lang, order_id: int, fmts: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fmt in fmts:
        if fmt == "docx":  # конспект приходит вместе с любым форматом
            continue
        key = "fmt_" + fmt
        label = t(lang, key) if key in TEXTS[Lang.RU] else fmt.upper()
        builder.button(text=label, callback_data=FmtCb(order_id=order_id, fmt=fmt))
    builder.button(text=t(lang, "fmt_all"), callback_data=FmtCb(order_id=order_id, fmt="all"))
    builder.adjust(2)
    return builder.as_markup()


def after_delivery(lang: Lang, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(t(lang, "btn_revise"), OrderCb(action="revise", order_id=order_id)),
                _btn(t(lang, "btn_all_good"), OrderCb(action="good", order_id=order_id)),
            ]
        ]
    )


def send_revision(lang: Lang, order_id: int) -> InlineKeyboardMarkup:
    return _rows(_btn(t(lang, "btn_send_revision"), OrderCb(action="send_revision", order_id=order_id)))


def rating(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("★" * n, RateCb(order_id=order_id, stars=n)) for n in range(1, 6)]]
    )


def credit_offer(lang: Lang, order_id: int, items: list[tuple[PlanCode, int]]) -> InlineKeyboardMarkup:
    return _rows(
        *(
            _btn(
                t(lang, "btn_credit", plan=t(lang, "plan_" + code.value), pay=money(pay)),
                PlanCb(code=code, credit=order_id),
            )
            for code, pay in items
        )
    )


def orders_list(lang: Lang, orders: list[Order]) -> InlineKeyboardMarkup:
    return _rows(
        *(
            _btn(
                t(lang, "order_row", id=o.id, status=t(lang, "st_" + o.status.value), topic=o.topic[:32]),
                OrderCb(action="show", order_id=o.id),
            )
            for o in orders
        )
    )


def order_actions(lang: Lang, order: Order) -> InlineKeyboardMarkup | None:
    s = OrderStatus
    rows: list[list[InlineKeyboardButton]] = []
    if not order.is_paid and order.price > 0 and order.status in (s.NEW, s.COVER, s.AWAITING_PAYMENT):
        rows.append([_btn(t(lang, "btn_pay"), OrderCb(action="pay", order_id=order.id))])
    if order.status in (s.DONE, s.REVISION) and order.deliver_dir:
        rows.append([_btn(t(lang, "btn_get_files"), OrderCb(action="files", order_id=order.id))])
    if order.status is s.DONE:
        rows.append([_btn(t(lang, "btn_revise"), OrderCb(action="revise", order_id=order.id))])
    if order.status in (s.DONE, s.CANCELLED):
        rows.append([_btn(t(lang, "btn_hide"), OrderCb(action="hide", order_id=order.id))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


# --- владелец и менеджеры (только по-русски) ---------------------------------


def staff_card(order: Order, *, stars_paid: bool) -> InlineKeyboardMarkup | None:
    s = OrderStatus
    b: list[tuple[str, MgrCb]] = []
    if order.status in (s.NEW, s.COVER, s.AWAITING_PAYMENT):
        b.append(("Отправить обложку", MgrCb(action="cover", order_id=order.id)))
    if not order.is_paid and order.price > 0 and order.status in (s.NEW, s.COVER, s.AWAITING_PAYMENT):
        b.append(("Оплата получена", MgrCb(action="paid", order_id=order.id)))
        b.append(("Изменить цену", MgrCb(action="price", order_id=order.id)))
    if order.status in (s.WORK, s.REVISION):
        b.append(("Отправить файлы", MgrCb(action="files", order_id=order.id)))
    # Ручная смена статуса — как в прежнем боте, если что-то сделали вне конвейера
    if order.is_paid and order.status in (s.COVER, s.AWAITING_PAYMENT):
        b.append(("▶️ В работу", MgrCb(action="st_work", order_id=order.id)))
    if order.status in (s.WORK, s.REVISION):
        b.append(("✅ Готово", MgrCb(action="st_done", order_id=order.id)))
    if order.status is s.DONE:
        b.append(("✏️ Правки", MgrCb(action="st_edit", order_id=order.id)))
    if order.status is not s.CANCELLED:
        if stars_paid:
            b.append(("Вернуть звёзды", MgrCb(action="refund", order_id=order.id)))
        else:
            b.append(("Отменить", MgrCb(action="cancel", order_id=order.id)))
    if not b:
        return None
    builder = InlineKeyboardBuilder()
    for text, cb in b:
        builder.button(text=text, callback_data=cb)
    builder.adjust(2)
    return builder.as_markup()


def staff_receipt(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Деньги пришли", MgrCb(action="pay_ok", payment_id=payment_id)),
                _btn("Не пришли", MgrCb(action="pay_no", payment_id=payment_id)),
            ]
        ]
    )


def staff_review(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Отправить клиенту", MgrCb(action="rv_send", order_id=order_id)),
                _btn("Доработать", MgrCb(action="rv_fix", order_id=order_id)),
            ]
        ]
    )


def staff_stuck(order_id: int, legacy: bool) -> InlineKeyboardMarkup:
    rows = (
        [
            [_btn("Сделать обложку", MgrCb(action="stk_cover", order_id=order_id))],
            [_btn("Сделать презентацию", MgrCb(action="stk_deck", order_id=order_id))],
        ]
        if legacy
        else [[_btn("Переделать", MgrCb(action="stk_redo", order_id=order_id))]]
    )
    rows.append([_btn("Не напоминать", MgrCb(action="stk_mute", order_id=order_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def staff_files_done(order_id: int) -> InlineKeyboardMarkup:
    return _rows(_btn("Готово — отправить клиенту", MgrCb(action="files_done", order_id=order_id)))


def staff_confirm(order_id: int, action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Да", MgrCb(action=action + "_yes", order_id=order_id)),
                _btn("Нет", MgrCb(action="noop", order_id=order_id)),
            ]
        ]
    )


def staff_send_canva(order_id: int) -> InlineKeyboardMarkup:
    return _rows(_btn("Отправить клиенту", MgrCb(action="send_canva", order_id=order_id)))
