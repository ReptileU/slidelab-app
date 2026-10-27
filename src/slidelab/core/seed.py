"""Начальные цены, тарифы, FAQ, стили и работы — те же, что сейчас в index.html.

Запуск: python -m slidelab.core.seed  (повторный запуск ничего не перезаписывает)
"""

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.config import get_settings
from slidelab.core.db import make_engine, make_sessionmaker
from slidelab.core.enums import PlanCode
from slidelab.core.models import FaqItem, PackagePlan, PortfolioWork, PriceRule, ShowcaseStyle
from slidelab.core.seed_faq import FAQ
from slidelab.core.seed_showcase import STYLES, WORKS

PRICE_RULE: dict[str, Any] = {
    "id": 1,
    "s10": 19_000,
    "s20": 29_000,
    "s30": 39_000,
    "urgent_pct": 50,
    "extra_text": 5_000,
    "extra_notes": 5_000,
    "first_order_s10": 9_900,
    "uzs_per_star": 155,  # ≈ $0.013 × 11 970 сум/$, что реально приходит при выводе звёзд
}

PLANS: list[dict[str, Any]] = [
    {"code": PlanCode.WEEK, "count": 2, "price": 34_000, "days": 14, "sort": 1},
    {"code": PlanCode.MONTH, "count": 4, "price": 64_000, "days": 30, "sort": 2},
    {
        "code": PlanCode.VIP,
        "count": 10,
        "price": 145_000,
        "days": 60,
        "notes_free": True,
        "priority": True,
        "max_parallel": 1,
        "sort": 3,
    },
]


async def seed(session: AsyncSession) -> None:
    if await session.get(PriceRule, 1) is None:
        session.add(PriceRule(**PRICE_RULE))
    for plan in PLANS:
        if await session.get(PackagePlan, plan["code"]) is None:
            session.add(PackagePlan(**plan))
    if await session.scalar(select(FaqItem.id).limit(1)) is None:
        session.add_all(FaqItem(texts=texts, sort=i) for i, texts in enumerate(FAQ, 1))
    if await session.scalar(select(ShowcaseStyle.id).limit(1)) is None:
        session.add_all(ShowcaseStyle(**style) for style in STYLES)
    if await session.scalar(select(PortfolioWork.id).limit(1)) is None:
        session.add_all(PortfolioWork(**work) for work in WORKS)
    await session.flush()


async def main() -> None:
    engine = make_engine(get_settings().database_url)
    async with make_sessionmaker(engine)() as session, session.begin():
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
