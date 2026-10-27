"""Сообщения клиенту и команде. Используется ботом, API и фоновыми задачами.

Команда — это личка владельца с ботом (как раньше) или супергруппа менеджеров с темами
(тема на клиента). В личке ответ реплаем на сообщение со строкой «ID: …» уходит клиенту.
"""

import html
import logging
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup, LabeledPrice, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.config import Settings
from slidelab.core import repositories as repo
from slidelab.core.enums import Lang, PaymentProvider, PaymentStatus, PlanCode
from slidelab.core.i18n import DEFAULT as DEFAULT_LANG
from slidelab.core.i18n import money, t
from slidelab.core.models import Order, ShowcaseStyle, User
from slidelab.core.models.base import utcnow
from slidelab.core.services.packages import Credit
from slidelab.core.services.payments import PaymentService
from slidelab.core.services.pricing import to_stars
from slidelab.telegram import keyboards as kb
from slidelab.telegram import legacy, views

log = logging.getLogger(__name__)


def lang_of(user: User) -> Lang:
    return user.lang or DEFAULT_LANG


class Notifier:
    def __init__(self, bot: Bot, session: AsyncSession, settings: Settings) -> None:
        self.bot = bot
        self.session = session
        self.settings = settings

    # --- клиент -----------------------------------------------------------------

    async def client(
        self,
        user: User,
        key: str,
        markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
        **kwargs: object,
    ) -> Message | None:
        text = t(user.lang, key, admin=self.settings.admin_username, **kwargs)
        return await self.client_text(user, text, markup)

    async def client_text(
        self, user: User, text: str, markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None
    ) -> Message | None:
        try:
            return await self.bot.send_message(user.tg_id, text, reply_markup=markup)
        except TelegramAPIError as e:  # клиент заблокировал бота и т.п.
            log.warning("Не удалось написать клиенту %s: %s", user.tg_id, e)
            return None

    async def menu(self, user: User) -> ReplyKeyboardMarkup:
        """Меню у поля ввода; в режиме старой витрины в нём кнопка с актуальными заказами клиента."""
        url = await self.app_url(user) if self.settings.legacy_webapp else None
        return kb.main_menu(lang_of(user), url)

    async def app_url(self, user: User, tab: str | None = None) -> str:
        """Адрес старой витрины с заказами и пакетом клиента в параметрах."""
        orders = [o for o in await repo.list_user_orders(self.session, user.id, limit=12) if not o.hidden]
        package = await repo.get_active_package(self.session, user.id, utcnow())
        first = None
        if not await repo.has_orders(self.session, user.id):
            first = (await repo.get_price_rule_row(self.session)).first_order_s10
        return legacy.webapp_url(
            self.settings.webapp_url,
            lang=user.lang,
            orders=orders,
            package=package,
            first_order_price=first,
            tab=tab,
        )

    def new_app_url(self, path: str = "") -> str:
        return self.settings.webapp_url.rstrip("/") + "/#/" + path

    # --- команда ----------------------------------------------------------------

    async def staff(
        self, text: str, markup: InlineKeyboardMarkup | None = None, user: User | None = None
    ) -> Message | None:
        chat_id = self.settings.staff_chat_id
        if chat_id is None:
            log.warning("ADMIN_ID не задан — сообщение команде потеряно: %s", text[:200])
            return None
        try:
            thread = await self._topic(user) if user else None
            return await self.bot.send_message(
                chat_id, text, reply_markup=markup, message_thread_id=thread, disable_web_page_preview=True
            )
        except TelegramAPIError as e:
            log.error("Не удалось написать команде: %s", e)
            return None

    async def copy_to_staff(self, message: Message, user: User, header: str | None = None) -> None:
        """Сообщение клиента — команде. Шапка с «ID:» позволяет ответить реплаем."""
        if header:
            who = html.escape(views.client_name(user))
            await self.staff(f"{header}\n{who} · ID: <code>{user.tg_id}</code>", user=user)
        chat_id = self.settings.staff_chat_id
        if chat_id is None:
            return
        try:
            thread = await self._topic(user)
            await message.copy_to(chat_id, message_thread_id=thread)
        except TelegramAPIError as e:
            log.error("Не удалось переслать команде: %s", e)

    async def post_card(self, order: Order, user: User) -> None:
        msg = await self.staff(await self._card_text(order, user), await self._card_markup(order), user)
        if msg is not None:
            order.managers_message_id = msg.message_id

    async def refresh_card(self, order: Order, note: str | None = None) -> None:
        """Обновить карточку после смены статуса; note — короткая строка в ленту."""
        user = await repo.get_user(self.session, order.user_id)
        chat_id = self.settings.staff_chat_id
        if chat_id is not None and order.managers_message_id is not None:
            try:
                await self.bot.edit_message_text(
                    await self._card_text(order, user),
                    chat_id=chat_id,
                    message_id=order.managers_message_id,
                    reply_markup=await self._card_markup(order),
                    disable_web_page_preview=True,
                )
            except TelegramAPIError as e:
                if "not modified" not in str(e):
                    log.warning("Карточка #%s не обновилась: %s", order.id, e)
        if note:
            await self.staff(f"#{order.id} · {note}", user=user)

    # --- оплата -----------------------------------------------------------------

    async def pay_block(
        self,
        user: User,
        *,
        amount: int,
        order: Order | None = None,
        plan: PlanCode | None = None,
        credit: Credit | None = None,
        early: bool = False,
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        """Реквизиты карт + кнопка оплаты звёздами (ссылка сразу открывает окно оплаты)."""
        lang = user.lang
        if plan is not None:
            head = t(lang, "pay_package", plan=t(lang, "plan_" + plan.value), price=money(amount))
            if credit:
                head += t(lang, "pay_credit", id=credit.order_id, amount=money(credit.amount))
            kind, ref = "plan", plan.value
        else:
            assert order is not None
            head = t(lang, "pay_order", id=order.id, price=money(amount))
            if early:
                head += t(lang, "pay_early")
            kind, ref = "order", str(order.id)

        stars = None
        stars_url = None
        if self.settings.stars:
            rate = (await repo.get_price_rule_row(self.session)).uzs_per_star
            stars = to_stars(amount, rate)
            stars_url = await self._stars_link(user, kind, ref, credit)

        cards = self.settings.pay_cards
        if cards:
            card_lines = "\n".join(f"{label}  <code>{html.escape(num)}</code>" for label, num in cards)
            name = t(lang, "pay_name", name=html.escape(self.settings.pay_name)) if self.settings.pay_name else ""
            body = t(lang, "pay_cards", cards=card_lines, name=name) + (t(lang, "pay_stars_too") if stars else "")
        else:
            body = t(lang, "pay_stars_only") if stars else t(lang, "pay_manual")
        markup = kb.pay(
            lang_of(user),
            stars=stars,
            stars_url=stars_url,
            kind=kind,
            ref=ref,
            cards=bool(cards),
            credit=credit.order_id if credit else 0,
        )
        return head + body, markup

    async def send_pay(
        self,
        user: User,
        *,
        amount: int,
        order: Order | None = None,
        plan: PlanCode | None = None,
        credit: Credit | None = None,
        early: bool = False,
    ) -> None:
        if amount <= 0:
            return
        text, markup = await self.pay_block(user, amount=amount, order=order, plan=plan, credit=credit, early=early)
        await self.client_text(user, text, markup)

    async def _stars_link(self, user: User, kind: str, ref: str, credit: Credit | None) -> str | None:
        """Счёт в звёздах — ссылкой. Платёж создаём сразу: оплата найдёт его по payload."""
        service = PaymentService(self.session)
        lang = user.lang
        try:
            if kind == "plan":
                code = PlanCode(ref)
                plan = await repo.get_plan(self.session, code)
                payment = await service.for_plan(
                    user.id, code, PaymentProvider.STARS, credit.order_id if credit else None
                )
                title = t(lang, "invoice_package", plan=t(lang, "plan_" + code.value))
                count = plan.count - (credit.units if credit else 0)
                desc = t(lang, "invoice_package_desc", count=count, days=plan.days)
            else:
                order = await repo.get_order(self.session, int(ref))
                payment = await service.for_order(order, PaymentProvider.STARS)
                title = t(lang, "invoice_order", id=order.id)
                slides = t(lang, "slides_" + order.slides.value)
                desc = t(lang, "invoice_order_desc", topic=order.topic[:80], slides=slides)
            return await self.bot.create_invoice_link(
                title=title[:32],
                description=desc[:255],
                payload=f"pay:{payment.id}",
                currency="XTR",
                prices=[LabeledPrice(label=title[:32], amount=payment.amount)],
            )
        except Exception as e:
            log.warning("Ссылка на оплату звёздами не создана: %s", e)
            return None

    # --- подарок за пакет -----------------------------------------------------

    async def send_gift(self, user: User, plan: PlanCode) -> None:
        spec = self.settings.gifts.get(plan.value, "")
        if not spec or datetime.now(UTC).date() > self.settings.gift_until:
            return
        emoji, _, stars_raw = spec.partition(":")
        stars = int(stars_raw or 0)
        who = f"{html.escape(views.client_name(user))}, ID <code>{user.tg_id}</code>"
        try:
            gifts = (await self.bot.get_available_gifts()).gifts
            same = [g for g in gifts if g.star_count == stars and g.remaining_count != 0]
            pick = next((g for g in same if g.sticker.emoji == emoji), None) or (same[0] if same else None)
            if pick is None:
                raise RuntimeError(f"нет подарка за {stars} ⭐")
            await self.bot.send_gift(gift_id=pick.id, user_id=user.tg_id, text=t(user.lang, "gift_text")[:128])
            await self.client(user, "gift_sent")
            await self.staff(f"🎁 {who}: отправлен подарок {emoji} ({stars} ⭐ с баланса бота)")
        except Exception as e:
            log.warning("Подарок не отправлен: %s", e)
            await self.staff(
                f"🎁 Не получилось отправить подарок {emoji} ({stars} ⭐) — {who}: {html.escape(str(e))[:150]}\n"
                "Скорее всего, на балансе бота мало звёзд. Подарите вручную: профиль клиента → ⋯ → «Отправить подарок»."
            )

    # --- внутреннее -------------------------------------------------------------

    async def _topic(self, user: User) -> int | None:
        """Тема клиента — только в супергруппе менеджеров."""
        if self.settings.managers_chat_id is None:
            return None
        if user.forum_topic_id is None:
            topic = await self.bot.create_forum_topic(
                self.settings.managers_chat_id, name=views.client_name(user)[:128]
            )
            user.forum_topic_id = topic.message_thread_id
            await self.session.flush()
        return user.forum_topic_id

    async def _card_text(self, order: Order, user: User) -> str:
        style = await self.session.get(ShowcaseStyle, order.style_id) if order.style_id else None
        style_name = (style.texts.get("ru") or {}).get("name") if style else None
        return views.staff_card(order, user, style_name)

    async def _card_markup(self, order: Order) -> InlineKeyboardMarkup | None:
        payment = await repo.latest_payment(self.session, order.id, PaymentStatus.PAID)
        stars_paid = payment is not None and payment.provider is PaymentProvider.STARS
        return kb.staff_card(order, stars_paid=stars_paid)
