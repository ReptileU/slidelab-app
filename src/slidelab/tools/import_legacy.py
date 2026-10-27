"""Перенос данных прежнего бота: orders.json и subs.json → база данных.

    uv run python -m slidelab.tools.import_legacy путь/к/старому/боту

Номера заказов сохраняются — по ним названы папки orders/<номер>/ конвейера.
Срок, язык и дизайн берутся из orders/<номер>/brief.json, если он есть.
Повторный запуск безопасен: уже перенесённые заказы и клиенты пропускаются.
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.config import Settings
from slidelab.core.db import make_engine, make_sessionmaker
from slidelab.core.enums import (
    Deadline,
    Design,
    Lang,
    LedgerReason,
    OrderSource,
    OrderStatus,
    PaidFrom,
    PaymentProvider,
    PaymentStatus,
    PlanCode,
    SlideTier,
    Stage,
)
from slidelab.core.models import Order, OrderEvent, PackageLedger, Payment, User, UserPackage

STATUS = {
    "new": OrderStatus.NEW,
    "cover": OrderStatus.COVER,
    "work": OrderStatus.WORK,
    "edit": OrderStatus.REVISION,
    "done": OrderStatus.DONE,
    "cancel": OrderStatus.CANCELLED,
}
DEADLINE_BY_LABEL = {"⚡": Deadline.URGENT, "🐢": Deadline.RELAXED}


@dataclass
class Report:
    users: int = 0
    orders: int = 0
    skipped: int = 0
    packages: int = 0


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _lang(value: object) -> Lang:
    try:
        return Lang(str(value))
    except ValueError:
        return Lang.RU


def _brief(work_dir: Path, order_id: int) -> dict[str, Any]:
    try:
        data = json.loads((work_dir / str(order_id) / "brief.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


async def _user(session: AsyncSession, tg_id: int, lang: Lang, name: str, report: Report) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, first_name=name or "Клиент", lang=lang)
        session.add(user)
        await session.flush()
        report.users += 1
    return user


async def import_orders(session: AsyncSession, data: dict[str, Any], work_dir: Path, report: Report) -> None:
    for raw in sorted(data.get("orders", {}).values(), key=lambda o: o["id"]):
        if await session.get(Order, raw["id"]) is not None:
            report.skipped += 1
            continue
        brief = _brief(work_dir, raw["id"])
        lang = _lang(raw.get("lang"))
        user = await _user(session, int(raw["uid"]), lang, str(brief.get("client", "")), report)
        status = STATUS.get(raw.get("status", "new"), OrderStatus.NEW)
        stage = Stage(raw["stage"]) if raw.get("stage") in Stage._value2member_map_ else None
        if status is OrderStatus.COVER and stage is Stage.COVER_OK:
            status = OrderStatus.AWAITING_PAYMENT
        deadline_label = str(brief.get("deadline", ""))
        created = _dt(raw.get("created")) or datetime.now(UTC)
        order = Order(
            id=raw["id"],
            user_id=user.id,
            topic=str(raw.get("topic") or brief.get("topic") or "—")[:300],
            slides=SlideTier(raw.get("slides", "s10")),
            deadline=next(
                (d for mark, d in DEADLINE_BY_LABEL.items() if deadline_label.startswith(mark)), Deadline.NORMAL
            ),
            pres_lang=_lang(brief.get("presentation_lang", lang.value)),
            design=Design.OWN if "шаблон клиента" in str(brief.get("design", "")) else Design.OURS,
            template_url=str(brief.get("template_link") or "")[:500] or None,
            extra_text=bool(brief.get("need_text")),
            extra_notes=bool(brief.get("need_notes")),
            need_humor=bool(brief.get("need_humor")),
            comment=str(brief.get("comment") or "")[:400] or None,
            sources=str(brief.get("sources") or "")[:1500] or None,
            has_source_files=bool(brief.get("client_will_send_files")),
            source=OrderSource.CHAT,
            ui_lang=lang,
            status=status,
            price=int(raw.get("price") or 0),
            paid_from=PaidFrom.PACKAGE if raw.get("sub") else PaidFrom.CASH,
            package_cost=int(raw.get("sub_cost") or 0),
            is_paid=bool(raw.get("paid")),
            stage=stage,
            stage_at=_dt(raw.get("stage_at")),
            alerted=raw.get("alerted"),
            alerted_at=_dt(raw.get("alerted_at")),
            no_alert=bool(raw.get("no_alert")),
            deliver_dir=raw.get("deliver_dir"),
            deliver_files=raw.get("deliver_files"),
            deliver_links=raw.get("deliver_links"),
            delivered=bool(raw.get("delivered")),
            result_link=raw.get("link"),
            hidden=bool(raw.get("hidden")),
            credit_until=_dt(raw.get("credit_until")),
            credit_used=bool(raw.get("credit_used")),
        )
        order.created_at = created
        session.add(order)
        await session.flush()
        session.add(
            OrderEvent(order_id=order.id, from_status=None, to_status=status, comment="перенесён из прежнего бота")
        )
        if raw.get("star_charge"):
            # оплата звёздами — платежом, чтобы работал возврат /refund
            session.add(
                Payment(
                    user_id=user.id,
                    order_id=order.id,
                    provider=PaymentProvider.STARS,
                    amount=int(raw.get("stars") or 0),
                    currency="XTR",
                    status=PaymentStatus.PAID,
                    external_id=raw["star_charge"],
                )
            )
        report.orders += 1


async def import_subs(session: AsyncSession, subs: dict[str, Any], report: Report) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    for uid, sub in subs.items():
        if sub.get("end", "") < today or sub.get("plan") not in PlanCode._value2member_map_:
            continue
        user = await _user(session, int(uid), Lang.RU, "", report)
        if await session.scalar(select(UserPackage.id).where(UserPackage.user_id == user.id)) is not None:
            continue  # пакет уже перенесён
        limit = int(sub.get("limit") or 0)
        left = max(0, limit - int(sub.get("used") or 0))
        expires = datetime.strptime(sub["end"], "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=UTC)
        package = UserPackage(
            user_id=user.id, plan_code=PlanCode(sub["plan"]), total=limit, left=left, expires_at=expires
        )
        session.add(package)
        await session.flush()
        session.add(PackageLedger(user_package_id=package.id, delta=left, reason=LedgerReason.GRANT))
        report.packages += 1


async def run(old_bot_dir: Path, settings: Settings) -> Report:
    report = Report()
    orders = json.loads((old_bot_dir / "orders.json").read_text(encoding="utf-8"))
    subs_file = old_bot_dir / "subs.json"
    subs = json.loads(subs_file.read_text(encoding="utf-8")) if subs_file.exists() else {}
    engine = make_engine(settings.database_url)
    async with make_sessionmaker(engine)() as session, session.begin():
        await import_orders(session, orders, old_bot_dir / "orders", report)
        await import_subs(session, subs, report)
        if engine.dialect.name == "postgresql":
            # следующий заказ продолжает старую нумерацию
            await session.execute(
                text("SELECT setval(pg_get_serial_sequence('orders', 'id'), (SELECT max(id) FROM orders))")
            )
    await engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Перенос orders.json и subs.json прежнего бота в базу")
    parser.add_argument(
        "old_bot_dir", type=Path, help="папка прежнего бота (где лежат orders.json, subs.json, orders/)"
    )
    args = parser.parse_args()
    report = asyncio.run(run(args.old_bot_dir, Settings()))
    print(
        f"Готово: заказов {report.orders} (пропущено как уже перенесённые: {report.skipped}), "
        f"новых клиентов {report.users}, пакетов {report.packages}."
    )


if __name__ == "__main__":
    main()
