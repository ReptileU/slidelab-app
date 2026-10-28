"""Совместимость со старой витриной index.html (GitHub Pages).

Старая витрина:
- открывается кнопкой меню с параметрами ?lang=&n=&s=&o= (заказы, пакет, цена первого заказа);
- шлёт действия через sendData (JSON) или ссылкой /start с кодом до 64 символов.

Когда новая Mini App заменит старую, модуль удаляется вместе с вызовами.
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pydantic import ValidationError

from slidelab.core.enums import Deadline, Design, Lang, OrderStatus, PlanCode, SlideTier
from slidelab.core.models import Order, UserPackage
from slidelab.core.schemas.order import OrderDraft
from slidelab.core.services.pipeline import formats_of

SLIDES = {"s10": SlideTier.S10, "s20": SlideTier.S20, "s30": SlideTier.S30}
DEADLINES = {"d1": Deadline.URGENT, "d2": Deadline.NORMAL, "d3": Deadline.RELAXED}
CODE_SLIDES = {"1": SlideTier.S10, "2": SlideTier.S20, "3": SlideTier.S30}
CODE_DEADLINES = {"1": Deadline.URGENT, "2": Deadline.NORMAL, "3": Deadline.RELAXED}
CODE_LANGS = {"r": Lang.RU, "u": Lang.UZ, "e": Lang.EN}
FORMATS = {"pptx", "pdf", "png", "gslides", "canva", "all"}
# Статусы, которые понимает старая витрина
OLD_STATUS = {
    OrderStatus.NEW: "new",
    OrderStatus.COVER: "cover",
    OrderStatus.AWAITING_PAYMENT: "cover",
    OrderStatus.WORK: "work",
    OrderStatus.REVISION: "edit",
    OrderStatus.DONE: "done",
    OrderStatus.CANCELLED: "cancel",
}


@dataclass(frozen=True, slots=True)
class LegacyOrder:
    draft: OrderDraft
    ui_lang: Lang
    style_name: str | None = None  # витрина присылает название стиля, а не ключ


@dataclass(frozen=True, slots=True)
class LegacyPlan:
    plan: PlanCode


@dataclass(frozen=True, slots=True)
class LegacyRevision:
    order_id: int
    text: str


@dataclass(frozen=True, slots=True)
class LegacyQuestion:
    text: str


@dataclass(frozen=True, slots=True)
class LegacyHide:
    order_id: int | None  # None — убрать все готовые и отменённые


@dataclass(frozen=True, slots=True)
class LegacyGetFormat:
    order_id: int
    fmt: str


LegacyAction = LegacyOrder | LegacyPlan | LegacyRevision | LegacyQuestion | LegacyHide | LegacyGetFormat


def parse_web_app_data(raw: str) -> LegacyAction | None:
    """JSON из tg.sendData старой витрины. None — если формат не распознан."""
    try:
        data: dict[str, Any] = json.loads(raw)
        kind = data.get("type")
        if kind == "sub":
            return LegacyPlan(PlanCode(data["plan"]))
        if kind == "edit":
            return LegacyRevision(int(data["id"]), str(data["text"])[:1500])
        if kind == "q":
            return LegacyQuestion(str(data["text"])[:1000])
        if kind == "hide":
            return _hide(str(data.get("id", "")))
        if kind == "get":
            return _get(str(data.get("id", "")), str(data.get("fmt", "")))
        if kind is None and data.get("v") == 1:
            return _order_from_json(data)
    except (ValueError, KeyError, TypeError, ValidationError):
        return None
    return None


def parse_start_payload(payload: str) -> LegacyAction | None:
    """Ссылка /start из старой витрины: код заявки, hide_<id|all>, get_<id>_<формат>."""
    if payload.startswith("hide_"):
        return _hide(payload[5:])
    if payload.startswith("get_"):
        parts = payload.split("_")
        return _get(parts[1], parts[2]) if len(parts) == 3 else None
    return parse_start_code(payload)


def _hide(ref: str) -> LegacyHide | None:
    if ref == "all":
        return LegacyHide(None)
    return LegacyHide(int(ref)) if ref.isdigit() else None


def _get(ref: str, fmt: str) -> LegacyGetFormat | None:
    return LegacyGetFormat(int(ref), fmt) if ref.isdigit() and fmt in FORMATS else None


def _order_from_json(data: dict[str, Any]) -> LegacyOrder:
    design = Design(data["design"])
    draft = OrderDraft(
        topic=data["topic"],
        slides=SLIDES[data["slides"]],
        deadline=DEADLINES[data["deadline"]],
        pres_lang=Lang(data["plang"]),
        design=design,
        template_url=(data.get("dlink") or None) if design is Design.OWN else None,
        extra_text=bool(data.get("text")),
        extra_notes=bool(data.get("notes")),
        need_humor=bool(data.get("humor")),
        contact=data.get("contact") or None,
        comment=(data.get("comment") or "")[:400] or None,
        sources=data.get("sources") or None,
        has_source_files=bool(data.get("srcfiles")),
    )
    return LegacyOrder(draft=draft, ui_lang=_lang(data.get("lang")), style_name=data.get("style") or None)


def parse_start_code(code: str) -> LegacyOrder | None:
    """Код заявки из /start.

    Формат: o + слайды + срок + язык + дизайн + текст + конспект + язык UI + тема в base64url.
    Заглавная буква языка UI — «С юмором».
    """
    if len(code) < 9 or code[0] != "o":
        return None
    try:
        topic_b64 = code[8:]
        topic = base64.urlsafe_b64decode(topic_b64 + "=" * (-len(topic_b64) % 4)).decode("utf-8", "ignore")
        draft = OrderDraft(
            topic=topic + ("…" if len(code) >= 64 else ""),
            slides=CODE_SLIDES[code[1]],
            deadline=CODE_DEADLINES[code[2]],
            pres_lang=CODE_LANGS[code[3]],
            design=Design.OWN if code[4] == "w" else Design.OURS,
            extra_text=code[5] == "1",
            extra_notes=code[6] == "1",
            need_humor=code[7].isupper(),
        )
        return LegacyOrder(draft=draft, ui_lang=CODE_LANGS.get(code[7].lower(), Lang.RU))
    except (KeyError, ValueError, ValidationError):
        return None


def order_formats(order: Order) -> list[str]:
    """Какие кнопки «Скачать» показать в витрине у готового заказа."""
    if not order.deliver_dir:
        return []
    fmts = [f for f in formats_of([Path(n) for n in order.deliver_files or []]) if f != "docx"]
    fmts += [k for k in ("gslides", "canva") if k in (order.deliver_links or {}) or "pptx" in fmts]
    return fmts


def order_row(order: Order) -> list[Any]:
    """Заказ для витрины: [id, тема, слайды, статус, цена(, ссылка, есть файл, просмотр, форматы)]."""
    row: list[Any] = [order.id, order.topic[:32], order.slides.value, OLD_STATUS[order.status], order.price]
    view = str((order.deliver_links or {}).get("view", ""))
    if order.result_link or order.deliver_dir or view:
        row += [
            (order.result_link or "")[:120],
            1 if order.deliver_dir else 0,
            view[:160],
            ",".join(order_formats(order)),
        ]
    return row


def webapp_url(
    base: str,
    *,
    lang: Lang | None,
    orders: list[Order],
    package: UserPackage | None,
    first_order_price: int | None,
    tab: str | None = None,
) -> str:
    """Адрес старой витрины с данными клиента — так она показывает трекер, «Мои работы», пакет и цены."""
    params: dict[str, str] = {}
    if lang:
        params["lang"] = lang.value
    if tab:
        params["tab"] = tab
    if orders:
        packed = json.dumps([order_row(o) for o in orders[:8]], ensure_ascii=False, separators=(",", ":")).encode()
        params["o"] = base64.urlsafe_b64encode(packed).decode().rstrip("=")
    if first_order_price:
        params["n"] = str(first_order_price)
    if package is not None:
        params["s"] = f"{package.plan_code.value}.{package.left}.{package.total}.{_date(package.expires_at)}"
    return f"{base}?{urlencode(params)}" if params else base


def _lang(value: object) -> Lang:
    try:
        return Lang(str(value))
    except ValueError:
        return Lang.RU


def _date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")
