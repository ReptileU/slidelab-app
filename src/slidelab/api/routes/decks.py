"""Конструктор презентаций в Mini App: список, создание, сохранение по слайдам, кредиты ИИ.

Сохранение всегда с `version`: если презентацию уже изменили в другом окне — 409 version_conflict,
клиент перезагружает её. Ответ на любое изменение — новая версия.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from slidelab.api.deps import SessionDep, ViewerDep
from slidelab.core.enums import DeckStatus, Lang
from slidelab.core.errors import DomainError
from slidelab.core.models import Deck
from slidelab.core.models.deck import DECK_TITLE_MAX
from slidelab.core.services import credits as cr
from slidelab.core.services.credits import CreditsService
from slidelab.core.services.decks import MAX_SLIDES, DeckService

router = APIRouter(tags=["decks"])

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DECK_TITLE_MAX)]


class DeckBrief(BaseModel):
    id: int
    title: str
    lang: Lang
    status: DeckStatus
    slides: int
    updated_at: datetime


class DeckOut(DeckBrief):
    version: int
    body: dict[str, Any]


class DeckVersionOut(BaseModel):
    id: int
    version: int
    updated_at: datetime


class DeckCreateIn(BaseModel):
    title: Title
    lang: Lang | None = None
    body: dict[str, Any] | None = None


class DeckMetaIn(BaseModel):
    version: int
    title: Title | None = None
    lang: Lang | None = None
    theme: dict[str, Any] | None = None


class SlideIn(BaseModel):
    version: int
    slide: dict[str, Any]
    after: str | None = None  # только для вставки: после какого слайда; None — в конец


class OrderIn(BaseModel):
    version: int
    order: list[str] = Field(max_length=MAX_SLIDES)


class CreditsOut(BaseModel):
    balance: int
    daily_cap: int
    costs: dict[str, int]


def _brief(deck: Deck) -> DeckBrief:
    return DeckBrief(
        id=deck.id,
        title=deck.title,
        lang=deck.lang,
        status=deck.status,
        slides=len(deck.body.get("slides", [])),
        updated_at=deck.updated_at,
    )


def _full(deck: Deck) -> DeckOut:
    return DeckOut(**_brief(deck).model_dump(), version=deck.version, body=deck.body)


def _ver(deck: Deck) -> DeckVersionOut:
    return DeckVersionOut(id=deck.id, version=deck.version, updated_at=deck.updated_at)


@router.get("/decks")
async def list_decks(viewer: ViewerDep, session: SessionDep) -> list[DeckBrief]:
    return [_brief(d) for d in await DeckService(session).list_for(viewer.user)]


@router.post("/decks", status_code=201)
async def create_deck(data: DeckCreateIn, viewer: ViewerDep, session: SessionDep) -> DeckOut:
    lang = data.lang or viewer.user.lang or Lang.RU
    deck = await DeckService(session).create(viewer.user, data.title, lang, data.body)
    await session.commit()
    return _full(deck)


@router.get("/decks/{deck_id}")
async def get_deck(deck_id: int, viewer: ViewerDep, session: SessionDep) -> DeckOut:
    return _full(await DeckService(session).get(viewer.user, deck_id))


@router.patch("/decks/{deck_id}")
async def update_deck(deck_id: int, data: DeckMetaIn, viewer: ViewerDep, session: SessionDep) -> DeckVersionOut:
    deck = await DeckService(session).update_meta(
        viewer.user, deck_id, data.version, title=data.title, lang=data.lang, theme=data.theme
    )
    await session.commit()
    return _ver(deck)


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(deck_id: int, viewer: ViewerDep, session: SessionDep) -> None:
    await DeckService(session).delete(viewer.user, deck_id)
    await session.commit()


@router.put("/decks/{deck_id}/slides/{slide_id}")
async def save_slide(
    deck_id: int, slide_id: str, data: SlideIn, viewer: ViewerDep, session: SessionDep
) -> DeckVersionOut:
    if data.slide.get("id") != slide_id:
        raise DomainError("id слайда в адресе и в теле не совпадает")
    deck = await DeckService(session).save_slide(viewer.user, deck_id, data.version, data.slide)
    await session.commit()
    return _ver(deck)


@router.post("/decks/{deck_id}/slides", status_code=201)
async def insert_slide(deck_id: int, data: SlideIn, viewer: ViewerDep, session: SessionDep) -> DeckVersionOut:
    deck = await DeckService(session).insert_slide(viewer.user, deck_id, data.version, data.slide, data.after)
    await session.commit()
    return _ver(deck)


@router.delete("/decks/{deck_id}/slides/{slide_id}")
async def delete_slide(
    deck_id: int, slide_id: str, version: int, viewer: ViewerDep, session: SessionDep
) -> DeckVersionOut:
    deck = await DeckService(session).delete_slide(viewer.user, deck_id, version, slide_id)
    await session.commit()
    return _ver(deck)


@router.put("/decks/{deck_id}/order")
async def reorder_slides(deck_id: int, data: OrderIn, viewer: ViewerDep, session: SessionDep) -> DeckVersionOut:
    deck = await DeckService(session).reorder(viewer.user, deck_id, data.version, data.order)
    await session.commit()
    return _ver(deck)


@router.get("/credits")
async def get_credits(viewer: ViewerDep, session: SessionDep) -> CreditsOut:
    balance = await CreditsService(session).balance(viewer.user)
    await session.commit()
    return CreditsOut(balance=balance, daily_cap=cr.DAILY_CAP, costs=cr.COSTS)
