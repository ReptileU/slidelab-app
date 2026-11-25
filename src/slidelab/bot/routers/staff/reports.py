"""Отчёты и выдача: /stats, /users, /subs, /grant."""

import html
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.enums import (
    LedgerReason,
    OrderStatus,
    PaymentStatus,
    PlanCode,
)
from slidelab.core.i18n import money, t
from slidelab.core.models import (
    Order,
    OrderEvent,
    Payment,
    Referral,
    User,
    UserPackage,
)
from slidelab.core.models.base import utcnow
from slidelab.core.services.packages import PackageService
from slidelab.telegram import views
from slidelab.telegram.flows import Flows

router = Router(name="staff_reports")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    now = utcnow()
    lines = ["<b>Статистика</b>"]
    for days in (7, 30):
        since = now - timedelta(days=days)
        created = await session.scalar(select(func.count(Order.id)).where(Order.created_at >= since)) or 0
        covers = await _reached(session, OrderStatus.COVER, since)
        started = await _reached(session, OrderStatus.WORK, since)
        uzs = await _revenue(session, since, "UZS")
        stars = await _revenue(session, since, "XTR")
        conversion = f"{started * 100 // covers}%" if covers else "—"
        lines.append(
            f"\n<b>{days} дней</b>\nЗаказов: {created}\n"
            f"Обложек: {covers} → в работу: {started} ({conversion})\n"
            f"Выручка: {money(uzs)} сум + {stars} ⭐"
        )
    await message.answer("\n".join(lines))


async def _reached(session: AsyncSession, status: OrderStatus, since: datetime) -> int:
    stmt = select(func.count(func.distinct(OrderEvent.order_id))).where(
        OrderEvent.to_status == status, OrderEvent.created_at >= since
    )
    return int(await session.scalar(stmt) or 0)


async def _revenue(session: AsyncSession, since: datetime, currency: str) -> int:
    stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.status == PaymentStatus.PAID, Payment.currency == currency, Payment.created_at >= since
    )
    return int(await session.scalar(stmt) or 0)


@router.message(Command("users"))
async def cmd_users(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """Кто заходил в бота: сколько новых за сутки / неделю / месяц и последние пришедшие.

    /users — последние 20, /users 50 — последние 50 (не больше 100). «Пришёл» — первый запуск бота
    или приложения; ✓ — оформил хоть один заказ, ← — по чьей ссылке пришёл."""
    arg = (command.args or "").strip()
    limit = min(int(arg), 100) if arg.isdigit() and int(arg) > 0 else 20
    now = utcnow()
    total = await session.scalar(select(func.count(User.id))) or 0
    counts = []
    for label, delta in (("сутки", timedelta(days=1)), ("7 дней", timedelta(days=7)), ("30 дней", timedelta(days=30))):
        n = await session.scalar(select(func.count(User.id)).where(User.created_at >= now - delta)) or 0
        counts.append(f"{label}: {n}")
    users = list(await session.scalars(select(User).order_by(User.id.desc()).limit(limit)))
    ordered = set(
        await session.scalars(
            select(Order.user_id).where(Order.user_id.in_([u.id for u in users])).group_by(Order.user_id)
        )
    )
    refs = dict(
        (
            await session.execute(
                select(Referral.friend_id, User.first_name)
                .join(User, User.id == Referral.inviter_id)
                .where(Referral.friend_id.in_([u.id for u in users]))
            )
        ).all()
    )
    lines = [f"<b>Пользователи</b> · всего {total}", "Новых — " + " · ".join(counts), ""]
    for u in users:
        name = html.escape(views.client_name(u))
        mark = " ✓" if u.id in ordered else ""
        via = f" ← {html.escape(refs[u.id] or '—')}" if u.id in refs else ""
        lines.append(f"• {name} <code>{u.tg_id}</code> — {views.date_short(u.created_at)}{mark}{via}")
    lines.append("\n✓ — заказывал · ← — пришёл по ссылке друга · /users 50 — показать больше")
    await message.answer("\n".join(lines))


@router.message(Command("subs"))
async def cmd_subs(message: Message, session: AsyncSession) -> None:
    rows = (
        await session.execute(
            select(UserPackage, User)
            .join(User, User.id == UserPackage.user_id)
            .where(UserPackage.expires_at > utcnow(), UserPackage.left > 0)
            .order_by(UserPackage.expires_at)
        )
    ).all()
    lines = [
        f"• {html.escape(views.client_name(u))} <code>{u.tg_id}</code> — {t(None, 'plan_' + p.plan_code.value)}, "
        f"осталось {p.left}/{p.total}, до {views.date_short(p.expires_at)}"
        for p, u in rows
    ]
    await message.answer("<b>Активные пакеты</b>\n" + ("\n".join(lines) if lines else "пока нет"))


@router.message(Command("grant"))
async def cmd_grant(message: Message, command: CommandObject, session: AsyncSession, flows: Flows) -> None:
    """/grant <Telegram ID> <week|month|vip> — выдать пакет без оплаты."""
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in PlanCode._value2member_map_:
        await message.answer("Формат: <code>/grant 123456789 month</code>")
        return
    client = await repo.get_user_by_tg(session, int(parts[0]))
    if client is None:
        await message.answer("Клиент ещё не писал боту — пусть нажмёт /start.")
        return
    package = await PackageService(session).activate(client.id, PlanCode(parts[1]), LedgerReason.GRANT)
    await session.commit()
    name = t(client.lang, "plan_" + package.plan_code.value)
    await flows.n.client(
        client,
        "pkg_on",
        await flows.n.menu(client),
        plan=name,
        left=package.left,
        date=views.date_short(package.expires_at),
    )
    await message.answer(f"Выдан пакет «{t(None, 'plan_' + package.plan_code.value)}» · осталось {package.left}")


# --- ответ клиенту ---------------------------------------------------------------------
