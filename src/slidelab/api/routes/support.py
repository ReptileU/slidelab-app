import html

from fastapi import APIRouter

from slidelab.api.deps import NotifierDep, SessionDep, ViewerDep
from slidelab.api.schemas import OkOut, ReviewIn, SupportIn
from slidelab.core import repositories as repo
from slidelab.core.enums import MessageDirection
from slidelab.core.models import Review, SupportMessage
from slidelab.telegram import views

router = APIRouter(tags=["support"])


@router.post("/support/messages")
async def ask(body: SupportIn, viewer: ViewerDep, session: SessionDep, notifier: NotifierDep) -> OkOut:
    session.add(SupportMessage(user_id=viewer.user.id, direction=MessageDirection.IN, text=body.text))
    await session.commit()
    await notifier.staff(
        f"❓ <b>Вопрос из приложения</b>\n{html.escape(views.client_name(viewer.user))}"
        f" · ID: <code>{viewer.user.tg_id}</code>\n\n{html.escape(body.text)}"
        "\n\n<i>Ответьте реплаем — перешлю клиенту.</i>",
        user=viewer.user,
    )
    await session.commit()
    return OkOut()


@router.post("/reviews")
async def review(body: ReviewIn, viewer: ViewerDep, session: SessionDep, notifier: NotifierDep) -> OkOut:
    if body.order_id is not None:
        order = await repo.get_order(session, body.order_id)
        if order.user_id != viewer.user.id:
            body = body.model_copy(update={"order_id": None})
    session.add(Review(user_id=viewer.user.id, order_id=body.order_id, stars=body.stars, text=body.text))
    await session.commit()
    where = f" к #{body.order_id}" if body.order_id else ""
    text = f"\n{html.escape(body.text)}" if body.text else ""
    await notifier.staff(f"⭐ Отзыв{where}: {'★' * body.stars}{text}", user=viewer.user)
    return OkOut()
