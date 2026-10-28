import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import Deadline, Design, OrderStatus, PaidFrom, PaymentProvider, PlanCode, Stage
from slidelab.core.models import Order, Payment, User, UserPackage
from slidelab.tools.import_legacy import Report, import_orders, import_subs

ORDERS = {
    "last_id": 13,
    "orders": {
        "12": {
            "id": 12, "uid": 1001, "lang": "uz", "topic": "Iqtisodiyot", "slides": "s20", "price": 29000,
            "status": "cover", "stage": "cover_ok", "created": "2026-10-20 10:00", "paid": False,
        },
        "13": {
            "id": 13, "uid": 1002, "lang": "ru", "topic": "История", "slides": "s10", "price": 0,
            "status": "done", "stage": "done", "sub": "month", "sub_cost": 1, "paid": True,
            "deliver_dir": "sent_deck_1025_1200", "deliver_files": ["deck.pptx"], "star_charge": "ch-1", "stars": 190,
        },
    },
}  # fmt: skip


async def test_import_keeps_ids_and_reads_brief(tmp_path: Path, session: AsyncSession) -> None:
    (tmp_path / "12").mkdir()
    (tmp_path / "12" / "brief.json").write_text(
        json.dumps(
            {
                "deadline": "⚡ Срочно (+50%)",
                "presentation_lang": "en",
                "design": "свой шаблон клиента",
                "template_link": "https://canva.com/t",
                "need_humor": True,
                "client": "Aziz",
            }
        ),
        encoding="utf-8",
    )
    report = Report()
    await import_orders(session, ORDERS, tmp_path, report)
    await import_orders(session, ORDERS, tmp_path, report)  # повторный запуск ничего не дублирует
    assert (report.orders, report.skipped, report.users) == (2, 2, 2)

    o12 = await session.get(Order, 12)
    assert o12 is not None
    assert (o12.status, o12.stage, o12.deadline, o12.design) == (
        OrderStatus.AWAITING_PAYMENT,
        Stage.COVER_OK,
        Deadline.URGENT,
        Design.OWN,
    )
    assert o12.need_humor and o12.template_url == "https://canva.com/t"
    user = await session.get(User, o12.user_id)
    assert user is not None and (user.tg_id, user.first_name) == (1001, "Aziz")

    o13 = await session.get(Order, 13)
    assert o13 is not None and (o13.paid_from, o13.package_cost, o13.is_paid) == (PaidFrom.PACKAGE, 1, True)
    payment = await session.scalar(select(Payment).where(Payment.order_id == 13))
    assert payment is not None and (payment.provider, payment.external_id) == (PaymentProvider.STARS, "ch-1")


async def test_import_active_packages_only(session: AsyncSession) -> None:
    future = (datetime.now(UTC) + timedelta(days=10)).strftime("%Y-%m-%d")
    subs = {
        "2001": {"plan": "month", "end": future, "used": 1, "limit": 4},
        "2002": {"plan": "week", "end": "2020-01-01", "used": 0, "limit": 2},
    }
    report = Report()
    await import_subs(session, subs, report)
    await import_subs(session, subs, report)
    assert report.packages == 1
    pkg = await session.scalar(select(UserPackage))
    assert pkg is not None and (pkg.plan_code, pkg.left, pkg.total) == (PlanCode.MONTH, 3, 4)
