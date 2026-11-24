"""/users — кто заходил в бота."""

from collections.abc import Callable
from typing import Any

from aiogram.filters import CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import FakeClock
from slidelab.bot.routers.staff import cmd_users
from slidelab.core.services.referrals import ReferralService, code_for
from test_orders import draft


class FakeMessage:
    def __init__(self) -> None:
        self.text = ""

    async def answer(self, text: str, **_: Any) -> None:
        self.text = text


async def test_users_lists_newcomers(session: AsyncSession, clock: FakeClock, make_user: Callable[..., Any]) -> None:
    from slidelab.core.services.orders import OrderService

    inviter = await make_user(username="timur")
    inviter.first_name = "Тимур"
    buyer = await make_user()
    buyer.first_name = "Азиз"
    await OrderService(session, clock).create(buyer.id, draft())
    friend = await make_user()
    friend.first_name = "Малика"
    await ReferralService(session, clock).attach(friend, code_for(inviter.id))
    await session.flush()

    msg = FakeMessage()
    await cmd_users(msg, CommandObject(prefix="/", command="users", args=None), session)  # type: ignore[arg-type]
    assert "всего 3" in msg.text
    assert msg.text.count("@timur") == 1
    assert "Азиз" in msg.text and "✓" in msg.text  # заказывал
    assert "Малика" in msg.text and "← Тимур" in msg.text  # пришла по ссылке
    # новые сверху
    assert msg.text.index("Малика") < msg.text.index("Азиз") < msg.text.index("@timur")
