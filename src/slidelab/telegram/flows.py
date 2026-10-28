"""Сценарии, общие для бота, API и фоновых задач: что сказать клиенту и команде и что записать для Claude."""

import html
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup
from sqlalchemy import select

from slidelab.core.enums import PaidFrom, PaymentProvider, PlanCode
from slidelab.core.i18n import money, t
from slidelab.core.models import Order, PackagePlan, ShowcaseStyle, User
from slidelab.core.services.payments import PaidResult, PaymentService
from slidelab.core.services.pipeline import Pipeline, fmt_of, formats_of
from slidelab.telegram import keyboards as kb
from slidelab.telegram import views
from slidelab.telegram.notifier import Notifier, lang_of

log = logging.getLogger(__name__)

PHOTO_MAX = 9_000_000


@dataclass(frozen=True, slots=True)
class Material:
    """Материал клиента: файл (по file_id) или текст."""

    name: str
    file_id: str | None = None
    text: str | None = None


class Flows:
    def __init__(self, notifier: Notifier) -> None:
        self.n = notifier
        self.bot = notifier.bot
        self.session = notifier.session
        self.settings = notifier.settings
        self.pipeline = Pipeline(notifier.settings.work_dir)

    # --- заказ создан -----------------------------------------------------------

    async def order_created(self, order: Order, user: User, materials: list[Material] | None = None) -> None:
        style = await self.session.get(ShowcaseStyle, order.style_id) if order.style_id else None
        style_name = (style.texts.get("ru") or {}).get("name") if style else None
        self.pipeline.write_brief(order, views.client_name(user), style_name)
        if materials:
            await self.save_materials(order.id, materials)

        await self.n.post_card(order, user)
        if materials:
            await self.materials_to_staff(order, user, materials)

        lang = user.lang
        package = ""
        if order.paid_from is PaidFrom.PACKAGE:
            balance = await PaymentService(self.session).packages.balance(user.id)
            package = t(lang, "package_used", cost=order.package_cost, left=balance.left if balance else 0)
            if order.price:
                package += t(lang, "package_extra", price=money(order.price))
        text = t(lang, "order_created", id=order.id, package=package)
        if order.design.value == "own" and not order.template_url:
            text += t(lang, "order_created_tpl")
        elif order.has_source_files:
            text += t(lang, "order_created_files")
        await self.n.client_text(user, text, await self.n.menu(user))

        if not order.is_paid and order.price > 0:
            await self.n.send_pay(user, amount=order.price, order=order, early=True)

    async def save_materials(self, order_id: int, materials: list[Material], sub: str = "files") -> None:
        """Материалы клиента — в папку заказа, чтобы Claude их видел."""
        for m in materials:
            try:
                if m.file_id:
                    await self.bot.download(m.file_id, destination=self.pipeline.material_path(order_id, m.name, sub))
                elif m.text:
                    self.pipeline.add_note(order_id, "Клиент (материал текстом)", m.text)
            except (TelegramAPIError, OSError) as e:
                log.warning("Материал к заказу #%s не скачался (%s) — он есть в чате", order_id, e)

    async def materials_to_staff(self, order: Order, user: User, materials: list[Material]) -> None:
        """Как в прежнем боте: материалы клиента — владельцу сразу под карточкой заказа."""
        chat_id = self.settings.staff_chat_id
        if chat_id is None:
            return
        await self.n.staff(
            f"📎 <b>Материалы к #{order.id}</b> · {len(materials)}\n"
            f"{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>",
            user=user,
        )
        thread = await self.n.topic_of(user)
        for m in materials:
            try:
                if m.file_id:
                    try:
                        await self.bot.send_document(chat_id, m.file_id, message_thread_id=thread)
                    except TelegramBadRequest:  # file_id фотографии документом не отправить
                        await self.bot.send_photo(chat_id, m.file_id, message_thread_id=thread)
                elif m.text:
                    await self.bot.send_message(chat_id, html.escape(m.text)[:4000], message_thread_id=thread)
            except TelegramAPIError as e:
                log.warning("Материал к заказу #%s не переслан владельцу: %s", order.id, e)

    # --- оплата -----------------------------------------------------------------

    async def announce_paid(self, result: PaidResult, user: User) -> None:
        if result.already_paid:
            return
        p = result.payment
        amount = f"{p.amount} ⭐" if p.currency == "XTR" else f"{money(p.amount)} сум"
        if result.attention:
            await self.n.staff(
                f"⚠️ {html.escape(result.attention)}\nПлатёж {p.id} · {amount}\n"
                f"{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>",
                user=user,
            )
        if result.package is not None:
            pkg = result.package
            name = t(user.lang, "plan_" + pkg.plan_code.value)
            await self.n.client(
                user, "pkg_on", await self.n.menu(user), plan=name, left=pkg.left, date=views.date_short(pkg.expires_at)
            )
            credit = f" · засчитан #{result.credit.order_id}" if result.credit else ""
            await self.n.staff(
                f"📦 Пакет «{t(None, 'plan_' + pkg.plan_code.value)}» оплачен{credit} · {amount}\n"
                f"{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code> · осталось {pkg.left}",
                user=user,
            )
            if p.plan_code is not None:
                await self.n.send_gift(user, p.plan_code)
        if result.order is not None and not (result.attention and not result.started):
            order = result.order
            self.pipeline.sync_status(order)
            self.pipeline.add_note(order.id, "Оплата", amount)
            if result.started:
                await self.n.client(user, "paid_go", id=order.id)
                await self.n.refresh_card(order, f"💰 оплачено {amount} — Claude делает презентацию")
            else:
                await self.n.client(user, "paid_early", id=order.id)
                await self.n.refresh_card(order, f"💰 оплачено {amount} — начнём после одобрения обложки")

    # --- обложка ----------------------------------------------------------------

    async def send_cover(self, order: Order, user: User, files: list[Path]) -> None:
        caption = t(user.lang, "cover_ready", id=order.id)
        await self.send_files(user.tg_id, files, caption, kb.cover(lang_of(user), order.id))

    async def send_cover_file(self, order: Order, user: User, file_id: str, *, photo: bool) -> None:
        """Обложка, которую менеджер прислал вручную (без конвейера)."""
        caption = t(user.lang, "cover_ready", id=order.id)
        markup = kb.cover(lang_of(user), order.id)
        if photo:
            await self.bot.send_photo(user.tg_id, file_id, caption=caption, reply_markup=markup)
        else:
            await self.bot.send_document(user.tg_id, file_id, caption=caption, reply_markup=markup)

    # --- выдача готового --------------------------------------------------------

    def available_formats(self, order: Order) -> list[str]:
        files = self.pipeline.delivered_files(order)
        fmts = formats_of(files)
        links = order.deliver_links or {}
        fmts += [k for k in ("gslides", "canva") if k in links or "pptx" in fmts]
        return fmts

    async def offer_formats(self, order: Order, user: User) -> None:
        fmts = self.available_formats(order)
        if len([f for f in fmts if f != "docx"]) > 1:
            await self.n.client(user, "formats_ask", kb.formats(lang_of(user), order.id, fmts), id=order.id)
        else:
            await self.deliver(order, user, "all")

    async def deliver(self, order: Order, user: User, choice: str) -> bool:
        """Прислать готовую презентацию в выбранном формате. Первая выдача — с подсказкой про правки."""
        files = self.pipeline.delivered_files(order)
        links = {k: v for k, v in (order.deliver_links or {}).items() if k != "view"}
        first = not order.delivered
        howto: list[str] = []
        if choice in ("gslides", "canva") and choice not in links:
            # ссылки нет — PPTX и короткая инструкция, как открыть его в своём аккаунте
            files = [f for f in files if fmt_of(f) == "pptx" or (first and fmt_of(f) == "docx")]
            howto, links = [choice], {}
        elif choice != "all":
            files = [f for f in files if fmt_of(f) == choice or (first and fmt_of(f) == "docx")]
            links = {k: v for k, v in links.items() if k == choice}
        if not files and not links:
            return False

        lang = user.lang
        caption = t(lang, "deck_ready", id=order.id) if first and not links else None
        if files:
            await self.send_files(user.tg_id, files, caption)
        for key, url in links.items():
            await self.n.client(user, "link_" + key, url=html.escape(url))
        for key in howto:
            await self.n.client(user, "how_" + key)
        if first:
            order.delivered = True
            await self.n.client(user, "after_delivery", kb.after_delivery(lang_of(user), order.id))
            await self.offer_credit(order, user)
        return True

    async def send_files(
        self, chat_id: int, files: list[Path], caption: str | None = None, markup: InlineKeyboardMarkup | None = None
    ) -> None:
        """Картинки — фото, остальное — документами. Подпись и кнопки — у последнего файла."""
        for i, f in enumerate(files):
            last = i == len(files) - 1
            cap, mk = (caption, markup) if last else (None, None)
            if f.suffix.lower() in (".png", ".jpg", ".jpeg") and f.stat().st_size < PHOTO_MAX:
                await self.bot.send_photo(chat_id, FSInputFile(f), caption=cap, reply_markup=mk)
            else:
                await self.bot.send_document(chat_id, FSInputFile(f), caption=cap, reply_markup=mk)

    # --- зачёт в пакет -----------------------------------------------------------

    async def offer_credit(self, order: Order, user: User) -> None:
        """После сдачи оплаченного заказа — предложить пакет с зачётом этого заказа."""
        payments = PaymentService(self.session)
        if not payments.packages.offer_credit(order, self.settings.credit_days):
            return
        plans = (
            await self.session.scalars(select(PackagePlan).where(PackagePlan.is_active).order_by(PackagePlan.sort))
        ).all()
        lang = user.lang
        lines, items = [], []
        for plan in plans:
            credit = await payments.packages.credit_for(order.id, plan.code)
            if credit is None:
                continue
            pay = plan.price - credit.amount
            lines.append(
                t(
                    lang,
                    "credit_line",
                    plan=t(lang, "plan_" + plan.code.value),
                    full=money(plan.price),
                    pay=money(pay),
                    more=plan.count - credit.units,
                )
            )
            items.append((plan.code, pay))
        if not items:
            return
        assert order.credit_until is not None
        await self.n.client(
            user,
            "credit_offer",
            kb.credit_offer(lang_of(user), order.id, items),
            date=views.date_short(order.credit_until),
            amount=money(order.price),
            lines="\n".join(lines),
        )

    async def plan_payment(self, user: User, code: PlanCode, credit_order_id: int = 0) -> bool:
        """Показать оплату пакета (с зачётом заказа, если он ещё действует)."""
        payments = PaymentService(self.session)
        q = await payments.plan_quote(code, credit_order_id or None, user.id)
        if credit_order_id and q.credit is None:
            return False
        await self.n.client(user, "pkg_requested", plan=t(user.lang, "plan_" + code.value))
        await self.n.send_pay(user, amount=q.amount, plan=code, credit=q.credit)
        # Счёт на перевод заводим сразу: как в прежнем боте, владелец может включить пакет одной кнопкой,
        # не дожидаясь чека (тот же счёт подхватит и чек клиента)
        payment = await payments.for_plan(
            user.id, code, PaymentProvider.MANUAL_CARD, q.credit.order_id if q.credit else None
        )
        await self.n.staff(
            f"📦 Заявка на пакет «{t(None, 'plan_' + code.value)}» — {money(q.amount)} сум"
            + (f" (засчитан #{q.credit.order_id})" if q.credit else "")
            + f"\n{html.escape(views.client_name(user))} · ID: <code>{user.tg_id}</code>\n"
            "<i>Реквизиты клиенту отправлены. Звёзды подтвердятся сами. Перевод пришёл — включите пакет:</i>",
            kb.staff_receipt(payment.id),
            user=user,
        )
        return True

    async def notify_status(self, order: Order, user: User) -> None:
        await self.n.client(
            user,
            "status_changed",
            await self.n.menu(user),
            id=order.id,
            status=t(user.lang, "st_" + order.status.value),
            topic=html.escape(order.topic[:60]),
        )

    async def sync(self, order: Order) -> None:
        self.pipeline.sync_status(order)
        await self.session.flush()
