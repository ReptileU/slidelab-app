import html

from fastapi import APIRouter
from sqlalchemy import select

from slidelab.api.deps import NotifierDep, SessionDep, ViewerDep
from slidelab.api.schemas import OkOut, ReviewIn, ReviewOut, SupportIn
from slidelab.core import repositories as repo
from slidelab.core.enums import MessageDirection
from slidelab.core.errors import NotFoundError
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


@router.get("/reviews/mine")
async def my_review(viewer: ViewerDep, session: SessionDep) -> ReviewOut | None:
    """Последний отзыв клиента — чтобы показать его в профиле и дать отозвать."""
    item = await session.scalar(
        select(Review).where(Review.user_id == viewer.user.id).order_by(Review.id.desc()).limit(1)
    )
    if item is None:
        return None
    return ReviewOut(id=item.id, order_id=item.order_id, stars=item.stars, text=item.text, created_at=item.created_at)


@router.delete("/reviews/{review_id}")
async def withdraw_review(review_id: int, viewer: ViewerDep, session: SessionDep, notifier: NotifierDep) -> OkOut:
    """Клиент передумал: отзыв удаляется, владельцу — сообщение, чтобы не публиковал отозванное."""
    item = await session.get(Review, review_id)
    if item is None or item.user_id != viewer.user.id:  # чужой отзыв для клиента — как несуществующий
        raise NotFoundError("Отзыв не найден")
    where = f" к #{item.order_id}" if item.order_id else ""
    text = f"\n{html.escape(item.text)}" if item.text else ""
    stars = "★" * item.stars
    await session.delete(item)
    await session.commit()
    await notifier.staff(
        f"↩️ <b>Клиент отозвал отзыв</b>{where}: {stars}{text}\n\n<i>Не публикуйте его.</i>", user=viewer.user
    )
    return OkOut()
