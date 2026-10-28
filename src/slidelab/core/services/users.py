from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core import repositories as repo
from slidelab.core.models import User


async def upsert_from_telegram(
    session: AsyncSession,
    *,
    tg_id: int,
    first_name: str,
    last_name: str | None,
    username: str | None,
    is_manager: bool = False,
) -> User:
    """Клиент из Telegram: создаём при первом контакте, имя и username держим свежими."""
    user = await repo.get_user_by_tg(session, tg_id)
    if user is None:
        user = User(tg_id=tg_id, first_name=first_name, last_name=last_name, username=username)
        session.add(user)
    else:
        user.first_name, user.last_name, user.username = first_name, last_name, username
    # Менеджеры задаются в .env — флаг синхронизируем при каждом контакте
    user.is_manager = is_manager
    await session.flush()
    return user
