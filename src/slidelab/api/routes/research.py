"""Помощник конструктора: поиск по бесплатным открытым источникам (без платного ИИ).

Всё — по запросу клиента: каждая кнопка в Mini App вызывает один из этих адресов.
Кредиты не списываются: источники бесплатные. Защита — не больше 30 запросов в минуту на человека.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from slidelab.api.deps import BotDep, SessionDep, SettingsDep, ViewerDep
from slidelab.api.routes.decks import AssetOut, _asset_out
from slidelab.core.enums import DeckAssetKind
from slidelab.core.services import research as rs
from slidelab.core.services.deck_assets import DeckAssetService, TelegramStore
from slidelab.core.services.decks import DeckService

router = APIRouter(prefix="/research", tags=["research"])

_default_fetcher = rs.HttpFetcher()


def get_research(request: Request, settings: SettingsDep, viewer: ViewerDep) -> rs.Research:
    rs.throttle(viewer.user.id)
    fetcher: rs.Fetcher = getattr(request.app.state, "research_fetcher", None) or _default_fetcher
    key = settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else None
    return rs.Research(fetcher, youtube_key=key)


ResearchDep = Annotated[rs.Research, Depends(get_research)]
Q = Annotated[str, Query(min_length=2, max_length=200)]


class SourcesOut(BaseModel):
    wiki: bool = True
    papers: bool = True
    photos: bool = True
    stats: bool = True
    videos: bool
    indicators: dict[str, str]


@router.get("/sources")
async def sources(settings: SettingsDep, viewer: ViewerDep) -> SourcesOut:
    """Какие кнопки показывать: видео — только когда добавлен ключ YouTube."""
    lang = str(viewer.user.lang or "ru")
    return SourcesOut(
        videos=settings.youtube_api_key is not None,
        indicators={k: v.get(lang, v["en"]) for k, v in rs.INDICATORS.items()},
    )


@router.get("/facts")
async def facts(q: Q, research: ResearchDep, lang: str = "ru") -> Any:
    return rs.dump(await research.facts(q, lang))


@router.get("/plan")
async def plan(q: Q, research: ResearchDep, lang: str = "ru") -> dict[str, Any] | None:
    result = await research.plan(q, lang)
    return rs.dump(result) if result else None


@router.get("/papers")
async def papers(q: Q, research: ResearchDep) -> Any:
    return rs.dump(await research.papers(q))


@router.get("/photos")
async def photos(q: Q, research: ResearchDep) -> Any:
    return rs.dump(await research.photos(q))


@router.get("/stats")
async def stats(
    research: ResearchDep,
    country: Annotated[str, Query(min_length=2, max_length=3)],
    indicator: Annotated[str, Query(max_length=40)],
    lang: str = "ru",
) -> Any:
    return rs.dump(await research.stats(country, indicator, lang))


@router.get("/videos")
async def videos(q: Q, research: ResearchDep, lang: str = "ru") -> Any:
    return rs.dump(await research.videos(q, lang))


class PhotoIn(BaseModel):
    url: str = Field(max_length=1000)


@router.post("/decks/{deck_id}/photo", status_code=201)
async def add_photo(
    deck_id: int,
    data: PhotoIn,
    research: ResearchDep,
    viewer: ViewerDep,
    session: SessionDep,
    bot: BotDep,
    settings: SettingsDep,
) -> AssetOut:
    """Найденное фото → в презентацию: сервер скачивает его (только с Wikimedia), сжимает и сохраняет."""
    deck = await DeckService(session).get(viewer.user, deck_id)
    blob = await research.download_photo(data.url)
    store = TelegramStore(bot, settings.deck_assets_chat_id)
    asset = await DeckAssetService(session, store).add(deck, DeckAssetKind.IMAGE, blob)
    await session.commit()
    return _asset_out(settings, asset)
