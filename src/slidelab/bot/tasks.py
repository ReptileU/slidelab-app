"""Фоновые задачи бота: результат от Claude → владельцу на проверку; сторож застрявших заказов."""

import asyncio
import html
import logging
from datetime import timedelta

import aiohttp
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slidelab.config import Settings
from slidelab.core import repositories as repo
from slidelab.core.models.base import as_utc, utcnow
from slidelab.core.services.orders import OrderService
from slidelab.core.services.pipeline import KIND_RU, REVIEW_OF, TODO, ReadyReview, safe_name
from slidelab.telegram import keyboards as kb
from slidelab.telegram.flows import Flows
from slidelab.telegram.notifier import Notifier

log = logging.getLogger(__name__)

REVIEW_EVERY = 20  # секунд
STUCK_EVERY = 600
STUCK_REPEAT = timedelta(hours=12)


async def watch_reviews(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Claude кладёт результат в orders/<id>/review/ + review.json → бот присылает владельцу на проверку."""
    while True:
        await asyncio.sleep(REVIEW_EVERY)
        try:
            async with sessionmaker() as session:
                await check_reviews(Flows(Notifier(bot, session, settings)), session)
        except Exception:
            log.exception("Проверка папки заказов")


async def check_reviews(flows: Flows, session: AsyncSession) -> int:
    orders = await repo.orders_in_stages(session, TODO)
    ready = flows.pipeline.ready_reviews(orders)
    for review in ready:
        await download_urls(flows, review)
        order = orders[review.order_id]
        files = flows.pipeline.review_files_pending(order.id)
        text = (
            f"🤖 <b>{KIND_RU.get(review.kind, review.kind)} к заказу #{order.id} готова — проверьте</b>\n"
            f"«{html.escape(order.topic[:80])}»"
        )
        if review.message:
            text += f"\n\n{html.escape(review.message)[:700]}"
        if review.canva:
            text += f"\n\nПоправить самому: {html.escape(review.canva)}"
        await flows.n.staff(text)
        caption = f"#{order.id} · {KIND_RU.get(review.kind, review.kind)}"
        if files:
            chat_id = flows.settings.staff_chat_id
            if chat_id is not None:
                await flows.send_files(chat_id, files, caption, kb.staff_review(order.id))
        else:
            await flows.n.staff(f"{caption}: файлов нет", kb.staff_review(order.id))
        flows.pipeline.mark_review_sent(order.id)
        OrderService(session).set_stage(order, REVIEW_OF[review.kind])
        await flows.sync(order)
        await session.commit()
    return len(ready)


async def download_urls(flows: Flows, review: ReadyReview) -> None:
    """Claude может дать ссылки (например, экспорт из Canva) — скачиваем их здесь."""
    if not review.urls:
        return
    folder = flows.pipeline.dir(review.order_id) / "review"
    async with aiohttp.ClientSession() as http:
        for item in review.urls:
            name = safe_name(item.get("name") or "file")
            target = folder / name
            if not target.exists():
                async with http.get(item["url"]) as resp:
                    resp.raise_for_status()
                    target.write_bytes(await resp.read())
            flows.pipeline.add_downloaded(review.order_id, name)


async def watch_stuck(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Сторож: заказ не сделан или застрял — предупредить владельца и дать кнопку «Переделать»."""
    await asyncio.sleep(60)
    while True:
        try:
            async with sessionmaker() as session:
                await check_stuck(Flows(Notifier(bot, session, settings)), session)
        except Exception:
            log.exception("Сторож заказов")
        await asyncio.sleep(STUCK_EVERY)


async def check_stuck(flows: Flows, session: AsyncSession) -> int:
    now = utcnow()
    alerted = 0
    for order in await repo.orders_to_watch(session):
        reason = flows.pipeline.stuck_reason(order, now, flows.settings.stuck_hours)
        if reason is None:
            continue
        key, why = reason
        if order.alerted == key and order.alerted_at and now - as_utc(order.alerted_at) < STUCK_REPEAT:
            continue
        await flows.n.staff(
            f"⚠️ <b>Заказ #{order.id} не сделан</b>\n«{html.escape(order.topic[:80])}»\n\n{html.escape(why)[:600]}",
            kb.staff_stuck(order.id, legacy=key == "legacy"),
        )
        order.alerted, order.alerted_at = key, now
        alerted += 1
    await session.commit()
    return alerted
