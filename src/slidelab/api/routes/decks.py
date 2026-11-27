"""Конструктор презентаций в Mini App: список, создание, сохранение по слайдам, кредиты ИИ.

Сохранение всегда с `version`: если презентацию уже изменили в другом окне — 409 version_conflict,
клиент перезагружает её. Ответ на любое изменение — новая версия.
"""

import base64
import binascii
import hashlib
import hmac
import time
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints

from slidelab.api.deps import BotDep, SessionDep, SettingsDep, ViewerDep
from slidelab.config import Settings
from slidelab.core.enums import DeckAssetKind, DeckStatus, Lang
from slidelab.core.errors import DomainError
from slidelab.core.models import Deck, DeckAsset
from slidelab.core.models.deck import DECK_TITLE_MAX
from slidelab.core.services import credits as cr
from slidelab.core.services.credits import CreditsService
from slidelab.core.services.deck_assets import AssetError, DeckAssetService, TelegramStore
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


class AssetIn(BaseModel):
    kind: DeckAssetKind = DeckAssetKind.IMAGE
    data: str = Field(max_length=17 * 1024 * 1024)  # base64 или data:image/...;base64,...


class AssetOut(BaseModel):
    id: int
    kind: DeckAssetKind
    width: int
    height: int
    bytes: int
    url: str  # относительный адрес с подписью: работает в <img> без заголовка Authorization


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


# --- Картинки ---------------------------------------------------------------

ASSET_URL_TTL = 24 * 3600


def _asset_sig(settings: Settings, asset_id: int, exp: int) -> str:
    key = hashlib.sha256(b"slidelab-deck-asset:" + settings.bot_token.get_secret_value().encode()).digest()
    return hmac.new(key, f"{asset_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def _asset_out(settings: Settings, asset: DeckAsset) -> AssetOut:
    # срок — до конца следующих суток (округлён), чтобы адрес картинки не менялся при каждом запросе и кэшировался
    exp = (int(time.time()) // ASSET_URL_TTL + 2) * ASSET_URL_TTL
    query = urlencode({"exp": exp, "sig": _asset_sig(settings, asset.id, exp)})
    return AssetOut(
        id=asset.id,
        kind=asset.kind,
        width=asset.width,
        height=asset.height,
        bytes=asset.bytes,
        url=f"/api/deck-assets/{asset.id}?{query}",
    )


def _decode(raw: str) -> bytes:
    data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise AssetError("Не получилось прочитать картинку — попробуйте другой файл") from None


@router.post("/decks/{deck_id}/assets", status_code=201)
async def upload_asset(
    deck_id: int, data: AssetIn, viewer: ViewerDep, session: SessionDep, bot: BotDep, settings: SettingsDep
) -> AssetOut:
    deck = await DeckService(session).get(viewer.user, deck_id)
    store = TelegramStore(bot, settings.deck_assets_chat_id)
    asset = await DeckAssetService(session, store).add(deck, data.kind, _decode(data.data))
    await session.commit()
    return _asset_out(settings, asset)


@router.get("/decks/{deck_id}/assets")
async def list_assets(
    deck_id: int, viewer: ViewerDep, session: SessionDep, bot: BotDep, settings: SettingsDep
) -> list[AssetOut]:
    deck = await DeckService(session).get(viewer.user, deck_id)
    store = TelegramStore(bot, settings.deck_assets_chat_id)
    return [_asset_out(settings, a) for a in await DeckAssetService(session, store).list_for(deck)]


@router.delete("/decks/{deck_id}/assets/{asset_id}", status_code=204)
async def delete_asset(
    deck_id: int, asset_id: int, viewer: ViewerDep, session: SessionDep, bot: BotDep, settings: SettingsDep
) -> None:
    deck = await DeckService(session).get(viewer.user, deck_id)
    await DeckAssetService(session, TelegramStore(bot, settings.deck_assets_chat_id)).delete(deck, asset_id)
    await session.commit()


@router.get("/deck-assets/{asset_id}")
async def asset_file(
    asset_id: int, exp: int, sig: str, session: SessionDep, bot: BotDep, settings: SettingsDep
) -> Response:
    """Картинка по подписанной ссылке — для <img> в Mini App (он не передаёт заголовки)."""
    if exp < time.time() or not hmac.compare_digest(sig, _asset_sig(settings, asset_id, exp)):
        raise HTTPException(status_code=403, detail="Ссылка устарела — откройте презентацию заново")
    asset = await session.get(DeckAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Нет такой картинки")
    data = await DeckAssetService(session, TelegramStore(bot, settings.deck_assets_chat_id)).read(asset)
    return Response(data, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400, immutable"})
