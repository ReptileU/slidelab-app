"""Конструктор презентаций: схема JSON презентации и сохранение по слайдам.

Презентация — один JSON (decks.body): тема и слайды. Координаты элементов — доли от 0 до 1, поэтому слайд
одинаково выглядит на телефоне и на ПК. Анимации — только имена пресетов: код анимаций живёт в Mini App.
Макеты совпадают с render/engine.py, чтобы экспорт шёл через тот же движок.
"""

import json
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import Lang
from slidelab.core.errors import DomainError, NotFoundError
from slidelab.core.models import Deck, User
from slidelab.core.models.base import utcnow

MAX_DECKS = 100  # презентаций у одного клиента
MAX_SLIDES = 60
MAX_ELEMENTS = 40  # на слайд
MAX_TEXT = 3000  # символов в одном текстовом элементе
MAX_BODY = 512 * 1024  # байт JSON на презентацию

LAYOUTS = (
    "blank", "cover", "hook", "bignum", "chart", "flow", "story", "three",
    "timeline", "split", "photo", "end", "sources",
)  # fmt: skip
ANIM_PRESETS = ("none", "fade", "fade-up", "zoom", "slide-left", "grow")

Unit = Annotated[float, Field(ge=0, le=1)]
Id = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")]
Color = Annotated[str, Field(max_length=16)]  # "#RRGGBB" или имя из палитры: "fg", "accent"…


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Box(Strict):
    x: Unit
    y: Unit
    w: Unit
    h: Unit


class Anim(Strict):
    preset: Literal[ANIM_PRESETS] = "none"  # type: ignore[valid-type]
    delay: float = Field(0, ge=0, le=10)
    trigger: Literal["slide", "click"] = "slide"


class TextStyle(Strict):
    size: float = Field(24, ge=6, le=200)
    weight: int = Field(400, ge=100, le=900)
    align: Literal["left", "center", "right"] = "left"
    color: Color = "fg"
    italic: bool = False


class Series(Strict):
    name: str = Field("", max_length=80)
    values: list[float] = Field(max_length=50)


class Chart(Strict):
    kind: Literal["bar", "line", "pie", "donut"]
    labels: list[Annotated[str, Field(max_length=60)]] = Field(max_length=50)
    series: list[Series] = Field(min_length=1, max_length=6)
    unit: str = Field("", max_length=30)
    legend: bool = False


class Crop(Strict):
    x: Unit = 0
    y: Unit = 0
    scale: float = Field(1, ge=1, le=5)


class Element(Strict):
    id: Id
    type: Literal["text", "image", "chart", "shape", "icon", "flag"]
    box: Box
    role: Literal["title", "subtitle", "body", "caption", "number", "quote"] | None = None
    text: str | None = Field(None, max_length=MAX_TEXT)
    style: TextStyle | None = None
    asset_id: int | None = None  # image: файл из deck_assets
    fit: Literal["cover", "contain"] = "cover"
    crop: Crop | None = None
    chart: Chart | None = None
    shape: Literal["rect", "round", "circle", "line", "arrow"] | None = None
    fill: Color | None = None
    icon: str | None = Field(None, max_length=40)  # имя иконки из библиотеки Mini App
    flag: str | None = Field(None, pattern=r"^[a-z]{2}$")  # код страны ISO 3166-1
    anim: Anim = Anim()


class Slide(Strict):
    id: Id
    layout: Literal[LAYOUTS] = "blank"  # type: ignore[valid-type]
    bg: Color | None = None
    bg_asset_id: int | None = None
    notes: str = Field("", max_length=MAX_TEXT)  # текст для выступления
    elements: list[Element] = Field(default_factory=list, max_length=MAX_ELEMENTS)


class Palette(Strict):
    bg: Color = "#0E1116"
    fg: Color = "#F5F5F5"
    accent: Color = "#FF5A36"
    muted: Color = "#8A94A6"


class Fonts(Strict):
    head: str = Field("Unbounded", max_length=40)
    body: str = Field("Montserrat", max_length=40)


class Logo(Strict):
    asset_id: int
    corner: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = "top-right"


class Background(Strict):
    asset_id: int
    overlay: float = Field(0.4, ge=0, le=1)


class Theme(Strict):
    palette: Palette = Palette()
    fonts: Fonts = Fonts()
    logo: Logo | None = None
    background: Background | None = None


class DeckBody(Strict):
    v: Literal[1] = 1
    theme: Theme = Theme()
    slides: list[Slide] = Field(default_factory=list, max_length=MAX_SLIDES)


class DeckLimitError(DomainError):
    code = "deck_limit"


class InvalidDeckError(DomainError):
    code = "invalid_deck"


class VersionConflictError(DomainError):
    """Презентацию уже изменили в другом окне — клиенту нужно перезагрузить её."""

    code = "version_conflict"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def blank_body(title: str) -> dict[str, Any]:
    cover = Slide(
        id=new_id(),
        layout="cover",
        elements=[
            Element(
                id=new_id(),
                type="text",
                role="title",
                box=Box(x=0.08, y=0.35, w=0.84, h=0.2),
                text=title,
                style=TextStyle(size=60, weight=700),
                anim=Anim(preset="fade-up"),
            )
        ],
    )
    return DeckBody(slides=[cover]).model_dump(mode="json")


def check_body(raw: dict[str, Any]) -> dict[str, Any]:
    """Проверить и нормализовать тело презентации. Ошибка — InvalidDeckError с понятным текстом."""
    try:
        body = DeckBody.model_validate(raw)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise InvalidDeckError(f"{where}: {first['msg']}") from e
    ids = [s.id for s in body.slides]
    if len(ids) != len(set(ids)):
        raise InvalidDeckError("Повторяется id слайда")
    data = body.model_dump(mode="json", exclude_none=True)
    if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_BODY:
        raise InvalidDeckError("Презентация слишком большая")
    return data


class DeckService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for(self, user: User) -> list[Deck]:
        rows = await self.session.scalars(
            select(Deck).where(Deck.user_id == user.id).order_by(Deck.updated_at.desc(), Deck.id.desc())
        )
        return list(rows)

    async def get(self, user: User, deck_id: int) -> Deck:
        deck = await self.session.get(Deck, deck_id)
        if deck is None or deck.user_id != user.id:
            raise NotFoundError("Нет такой презентации")
        return deck

    async def create(self, user: User, title: str, lang: Lang, body: dict[str, Any] | None = None) -> Deck:
        count = await self.session.scalar(select(func.count(Deck.id)).where(Deck.user_id == user.id))
        if (count or 0) >= MAX_DECKS:
            raise DeckLimitError(f"Не больше {MAX_DECKS} презентаций")
        deck = Deck(
            user_id=user.id,
            title=title,
            lang=lang,
            body=check_body(body) if body is not None else blank_body(title),
        )
        self.session.add(deck)
        await self.session.flush()
        return deck

    async def _write(self, deck: Deck, version: int, body: dict[str, Any], **fields: Any) -> Deck:
        """Записать новое тело, только если в базе всё ещё `version` (иначе кто-то сохранил раньше)."""
        body = check_body(body)
        result = await self.session.execute(
            update(Deck)
            .where(Deck.id == deck.id, Deck.version == version)
            .values(body=body, version=version + 1, updated_at=utcnow(), **fields)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise VersionConflictError("Презентацию уже изменили — откройте её заново")
        await self.session.refresh(deck)
        return deck

    async def save_slide(self, user: User, deck_id: int, version: int, slide: dict[str, Any]) -> Deck:
        """Сохранить один слайд: заменить слайд с тем же id или добавить новый в конец."""
        deck = await self.get(user, deck_id)
        slides = list(deck.body.get("slides", []))
        idx = next((i for i, s in enumerate(slides) if s.get("id") == slide.get("id")), None)
        if idx is None:
            slides.append(slide)
        else:
            slides[idx] = slide
        return await self._write(deck, version, {**deck.body, "slides": slides})

    async def insert_slide(
        self, user: User, deck_id: int, version: int, slide: dict[str, Any], after: str | None
    ) -> Deck:
        deck = await self.get(user, deck_id)
        slides = list(deck.body.get("slides", []))
        pos = len(slides)
        if after is not None:
            pos = next((i + 1 for i, s in enumerate(slides) if s.get("id") == after), pos)
        slides.insert(pos, slide)
        return await self._write(deck, version, {**deck.body, "slides": slides})

    async def delete_slide(self, user: User, deck_id: int, version: int, slide_id: str) -> Deck:
        deck = await self.get(user, deck_id)
        slides = [s for s in deck.body.get("slides", []) if s.get("id") != slide_id]
        return await self._write(deck, version, {**deck.body, "slides": slides})

    async def reorder(self, user: User, deck_id: int, version: int, order: list[str]) -> Deck:
        deck = await self.get(user, deck_id)
        slides = {s["id"]: s for s in deck.body.get("slides", [])}
        if sorted(order) != sorted(slides):
            raise InvalidDeckError("Порядок должен содержать все слайды ровно по разу")
        return await self._write(deck, version, {**deck.body, "slides": [slides[i] for i in order]})

    async def update_meta(
        self,
        user: User,
        deck_id: int,
        version: int,
        *,
        title: str | None = None,
        lang: Lang | None = None,
        theme: dict[str, Any] | None = None,
    ) -> Deck:
        deck = await self.get(user, deck_id)
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if lang is not None:
            fields["lang"] = lang
        body = {**deck.body, "theme": theme} if theme is not None else deck.body
        return await self._write(deck, version, body, **fields)

    async def delete(self, user: User, deck_id: int) -> None:
        deck = await self.get(user, deck_id)
        await self.session.delete(deck)
        await self.session.flush()
