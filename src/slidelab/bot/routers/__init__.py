from aiogram import Router

from slidelab.bot.routers import errors, fallback, legacy, order, orders, payments, staff, start, support


def build_router(extra: Router | None = None) -> Router:
    """Порядок важен: команда и оплата — раньше всех, свободная переписка (support) — последней.

    extra — публикация постов: после команды, до клиентских сценариев.
    """
    root = Router(name="root")
    root.include_routers(errors.router, staff.router)
    if extra is not None:
        root.include_router(extra)
    root.include_routers(
        payments.router,
        start.router,
        legacy.router,
        order.router,
        orders.router,
        support.router,
        fallback.router,
    )
    return root
