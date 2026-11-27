"""Помощник конструктора без платного ИИ: бесплатные открытые источники.

- Википедия: факты (краткое описание), план (разделы статьи), связанные темы для сюжета;
- OpenAlex: научные статьи (автор, год, цитирования, ссылка, начало аннотации);
- Wikimedia Commons: свободные фото с автором и лицензией;
- World Bank: статистика по странам для графиков;
- YouTube: видео — только если задан бесплатный ключ YOUTUBE_API_KEY.

Ответы кэшируются в памяти на сутки: одинаковые темы у разных клиентов не гоняют запросы заново.
Тексты из источников не копируются в слайды целиком: клиент видит краткую выжимку и ссылку.
"""

import asyncio
import html
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import aiohttp

from slidelab.core.errors import DomainError

UA = "SlideLabBot/1.0 (https://t.me/slidelab_uz)"  # Википедия просит представляться
TTL = 24 * 3600
TIMEOUT = 12

# Откуда разрешено скачивать картинку на сервер (защита: сервер не ходит по произвольным адресам)
PHOTO_HOSTS = {"upload.wikimedia.org"}

# Показатели World Bank, понятные школьникам и студентам
INDICATORS: dict[str, dict[str, str]] = {
    "SP.POP.TOTL": {"ru": "Население", "uz": "Aholi", "en": "Population"},
    "NY.GDP.MKTP.CD": {"ru": "ВВП, $", "uz": "YaIM, $", "en": "GDP, $"},
    "NY.GDP.PCAP.CD": {"ru": "ВВП на человека, $", "uz": "Aholi jon boshiga YaIM, $", "en": "GDP per capita, $"},
    "NY.GDP.MKTP.KD.ZG": {"ru": "Рост ВВП, %", "uz": "YaIM o'sishi, %", "en": "GDP growth, %"},
    "NE.EXP.GNFS.CD": {"ru": "Экспорт, $", "uz": "Eksport, $", "en": "Exports, $"},
    "NE.IMP.GNFS.CD": {"ru": "Импорт, $", "uz": "Import, $", "en": "Imports, $"},
    "FP.CPI.TOTL.ZG": {"ru": "Инфляция, %", "uz": "Inflyatsiya, %", "en": "Inflation, %"},
    "SL.UEM.TOTL.ZS": {"ru": "Безработица, %", "uz": "Ishsizlik, %", "en": "Unemployment, %"},
    "SP.URB.TOTL.IN.ZS": {"ru": "Городское население, %", "uz": "Shahar aholisi, %", "en": "Urban population, %"},
    "SP.DYN.LE00.IN": {"ru": "Продолжительность жизни", "uz": "Umr davomiyligi", "en": "Life expectancy"},
    "IT.NET.USER.ZS": {
        "ru": "Пользователи интернета, %",
        "uz": "Internet foydalanuvchilari, %",
        "en": "Internet users, %",
    },
    "EG.ELC.ACCS.ZS": {"ru": "Доступ к электричеству, %", "uz": "Elektrga ega, %", "en": "Access to electricity, %"},
    "AG.LND.FRST.ZS": {"ru": "Леса, % территории", "uz": "O'rmonlar, % hudud", "en": "Forest, % of land"},
    "BX.TRF.PWKR.CD.DT": {"ru": "Денежные переводы, $", "uz": "Pul o'tkazmalari, $", "en": "Remittances, $"},
}


class ResearchError(DomainError):
    code = "research_failed"


class SourceDisabledError(DomainError):
    code = "source_disabled"


class Fetcher(Protocol):
    async def json(self, url: str, params: dict[str, Any] | None = None) -> Any: ...
    async def bytes(self, url: str) -> bytes: ...


class HttpFetcher:
    """Обычные HTTP-запросы (aiohttp уже есть у бота — отдельная библиотека не нужна)."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    def _s(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=TIMEOUT)
            )
        return self._session

    async def json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._s().get(url, params=params) as r:
                r.raise_for_status()
                return await r.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise ResearchError(f"Источник не ответил: {urlparse(url).netloc}") from e

    async def bytes(self, url: str) -> bytes:
        try:
            async with self._s().get(url) as r:
                r.raise_for_status()
                return await r.content.read(13 * 1024 * 1024)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise ResearchError("Не получилось скачать картинку") from e


# --- ответы ---------------------------------------------------------------


@dataclass(slots=True)
class Fact:
    title: str
    text: str  # краткая выжимка
    url: str
    image: str | None = None


@dataclass(slots=True)
class PlanItem:
    title: str
    level: int  # 1 — раздел, 2 — подраздел


@dataclass(slots=True)
class Plan:
    source_title: str
    url: str
    items: list[PlanItem] = field(default_factory=list)
    history: list[str] = field(default_factory=list)  # подразделы истории — готовые сюжетные ходы


@dataclass(slots=True)
class Paper:
    title: str
    year: int | None
    authors: str
    cited: int
    url: str
    abstract: str


@dataclass(slots=True)
class Photo:
    title: str
    thumb: str
    url: str  # полный файл (для добавления на слайд)
    page: str  # страница файла на Commons (автор и лицензия)
    author: str
    license: str
    width: int
    height: int


@dataclass(slots=True)
class Stats:
    country: str
    indicator: str
    label: str
    labels: list[str]
    values: list[float]
    url: str


@dataclass(slots=True)
class Video:
    title: str
    channel: str
    url: str
    thumb: str
    published: str


def dump(obj: Any) -> Any:
    if isinstance(obj, list):
        return [dump(o) for o in obj]
    return asdict(obj)


# --- кэш ------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_MAX = 2000


async def cached(key: str, make: Callable[[], Awaitable[Any]]) -> Any:
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = await make()
    if len(_cache) >= _CACHE_MAX:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[: _CACHE_MAX // 4]:
            _cache.pop(k, None)
    _cache[key] = (time.monotonic() + TTL, value)
    return value


# --- помощники ------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
SKIP_SECTIONS = {
    "ru": ("примечания", "литература", "ссылки", "см. также", "источники", "галерея", "комментарии"),
    "uz": ("manbalar", "havolalar", "adabiyot", "izohlar", "yana qarang"),
    "en": (
        "references",
        "notes",
        "external links",
        "see also",
        "further reading",
        "bibliography",
        "sources",
        "gallery",
    ),
}
HISTORY_WORDS = ("истори", "tarix", "histor")


def clean(text: str) -> str:
    # знаки ударения Википедии («Ара́льское») в слайде не нужны
    return html.unescape(_TAG.sub("", text)).replace("\u0301", "").strip()


def short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def wiki_lang(lang: str) -> str:
    return lang if lang in ("ru", "uz", "en") else "ru"


class Research:
    def __init__(self, fetcher: Fetcher, youtube_key: str | None = None) -> None:
        self.f = fetcher
        self.youtube_key = youtube_key

    # Википедия -------------------------------------------------------------

    async def _wiki_titles(self, q: str, lang: str, limit: int) -> list[str]:
        data = await self.f.json(
            f"https://{lang}.wikipedia.org/w/api.php",
            {"action": "query", "list": "search", "srsearch": q, "srlimit": limit, "format": "json", "utf8": 1},
        )
        return [s["title"] for s in data.get("query", {}).get("search", [])]

    async def _summary(self, title: str, lang: str) -> Fact | None:
        data = await self.f.json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        )
        if data.get("type") == "disambiguation" or not data.get("extract"):
            return None
        return Fact(
            title=data.get("title", title),
            text=short(clean(data["extract"]), 420),
            url=data.get("content_urls", {})
            .get("desktop", {})
            .get("page", f"https://{lang}.wikipedia.org/wiki/{quote(title)}"),
            image=(data.get("thumbnail") or {}).get("source"),
        )

    async def facts(self, q: str, lang: str) -> list[Fact]:
        """Главная статья по теме и соседние — короткие справки со ссылкой."""
        lang = wiki_lang(lang)

        async def make() -> list[Fact]:
            titles = await self._wiki_titles(q, lang, 6)
            found = await asyncio.gather(*(self._summary(t, lang) for t in titles), return_exceptions=True)
            return [f for f in found if isinstance(f, Fact)]

        return list(await cached(f"facts:{lang}:{q.lower()}", make))

    async def plan(self, q: str, lang: str) -> Plan | None:
        """План по разделам главной статьи + подразделы истории как сюжетные ходы."""
        lang = wiki_lang(lang)

        async def make() -> Plan | None:
            titles = await self._wiki_titles(q, lang, 1)
            if not titles:
                return None
            data = await self.f.json(
                f"https://{lang}.wikipedia.org/w/api.php",
                {"action": "parse", "page": titles[0], "prop": "sections", "format": "json", "redirects": 1},
            )
            sections = data.get("parse", {}).get("sections", [])
            skip = SKIP_SECTIONS[lang]
            items: list[PlanItem] = []
            history: list[str] = []
            in_history = False
            for s in sections:
                name = clean(s.get("line", ""))
                level = int(s.get("toclevel", 1))
                if not name or name.lower() in skip:
                    in_history = False if level == 1 else in_history
                    continue
                if level == 1:
                    in_history = any(w in name.lower() for w in HISTORY_WORDS)
                    items.append(PlanItem(name, 1))
                elif level == 2:
                    items.append(PlanItem(name, 2))
                    if in_history:
                        history.append(name)
            return Plan(
                source_title=titles[0],
                url=f"https://{lang}.wikipedia.org/wiki/{quote(titles[0].replace(' ', '_'))}",
                items=items[:40],
                history=history[:12],
            )

        result: Plan | None = await cached(f"plan:{lang}:{q.lower()}", make)
        return result

    # OpenAlex --------------------------------------------------------------

    async def papers(self, q: str) -> list[Paper]:
        async def make() -> list[Paper]:
            data = await self.f.json(
                "https://api.openalex.org/works",
                {
                    "search": q,
                    "per-page": 10,
                    "select": "id,display_name,publication_year,doi,cited_by_count,authorships,abstract_inverted_index",
                },
            )
            out = []
            for w in data.get("results", []):
                authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:3]]
                more = " и др." if len(w.get("authorships", [])) > 3 else ""
                out.append(
                    Paper(
                        title=clean(w.get("display_name") or ""),
                        year=w.get("publication_year"),
                        authors=", ".join(a for a in authors if a) + more,
                        cited=int(w.get("cited_by_count") or 0),
                        url=w.get("doi") or w.get("id", ""),
                        abstract=short(_abstract(w.get("abstract_inverted_index")), 360),
                    )
                )
            return [p for p in out if p.title]

        return list(await cached(f"papers:{q.lower()}", make))

    # Wikimedia Commons -----------------------------------------------------

    async def photos(self, q: str) -> list[Photo]:
        async def make() -> list[Photo]:
            data = await self.f.json(
                "https://commons.wikimedia.org/w/api.php",
                {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"{q} filetype:bitmap",
                    "gsrnamespace": 6,
                    "gsrlimit": 16,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata|size|mime",
                    "iiurlwidth": 640,
                    "format": "json",
                },
            )
            pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
            out = []
            for p in pages:
                info = (p.get("imageinfo") or [{}])[0]
                if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                    continue
                meta = info.get("extmetadata", {})
                out.append(
                    Photo(
                        title=clean(p.get("title", "")).removeprefix("File:").rsplit(".", 1)[0],
                        thumb=info.get("thumburl") or info.get("url", ""),
                        url=info.get("url", ""),
                        page=info.get("descriptionurl", ""),
                        author=short(clean(meta.get("Artist", {}).get("value", "")), 80),
                        license=clean(meta.get("LicenseShortName", {}).get("value", "")),
                        width=int(info.get("width") or 0),
                        height=int(info.get("height") or 0),
                    )
                )
            return out

        return list(await cached(f"photos:{q.lower()}", make))

    async def download_photo(self, url: str) -> bytes:
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in PHOTO_HOSTS:
            raise ResearchError("Картинку можно взять только из найденных помощником")
        return await self.f.bytes(url)

    # World Bank ------------------------------------------------------------

    async def stats(self, country: str, indicator: str, lang: str) -> Stats:
        if indicator not in INDICATORS:
            raise ResearchError("Нет такого показателя")
        if not re.fullmatch(r"[A-Za-z]{2,3}", country):
            raise ResearchError("Код страны — две или три латинские буквы")
        country = country.upper()

        async def make() -> Stats:
            data = await self.f.json(
                f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}",
                {"format": "json", "per_page": 80, "date": "1960:2030"},
            )
            rows = data[1] if isinstance(data, list) and len(data) > 1 and data[1] else []
            points = sorted((int(r["date"]), float(r["value"])) for r in rows if r.get("value") is not None)
            if not points:
                raise ResearchError("По этой стране нет данных")
            name = rows[0].get("country", {}).get("value", country)
            return Stats(
                country=name,
                indicator=indicator,
                label=INDICATORS[indicator].get(wiki_lang(lang), INDICATORS[indicator]["en"]),
                labels=[str(y) for y, _ in points],
                values=[v for _, v in points],
                url=f"https://data.worldbank.org/indicator/{indicator}?locations={country}",
            )

        result: Stats = await cached(f"stats:{country}:{indicator}:{lang}", make)
        return result

    # YouTube ---------------------------------------------------------------

    async def videos(self, q: str, lang: str) -> list[Video]:
        if not self.youtube_key:
            raise SourceDisabledError("Поиск видео пока не подключён")
        key = self.youtube_key

        async def make() -> list[Video]:
            data = await self.f.json(
                "https://www.googleapis.com/youtube/v3/search",
                {
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 8,
                    "q": q,
                    "relevanceLanguage": wiki_lang(lang),
                    "safeSearch": "strict",
                    "key": key,
                },
            )
            out = []
            for it in data.get("items", []):
                vid = it.get("id", {}).get("videoId")
                sn = it.get("snippet", {})
                if not vid:
                    continue
                out.append(
                    Video(
                        title=clean(sn.get("title", "")),
                        channel=clean(sn.get("channelTitle", "")),
                        url=f"https://www.youtube.com/watch?v={vid}",
                        thumb=sn.get("thumbnails", {}).get("medium", {}).get("url", ""),
                        published=(sn.get("publishedAt") or "")[:10],
                    )
                )
            return out

        # YouTube: квота ~100 поисков в день — кэш особенно важен
        return list(await cached(f"videos:{lang}:{q.lower()}", make))


def _abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex хранит аннотацию как «слово → позиции»: собираем обратно."""
    if not inverted:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for pos in positions:
            if pos < 120:
                words[pos] = word
    return " ".join(words[i] for i in sorted(words))


# --- защита от частых запросов ----------------------------------------------

_hits: dict[int, list[float]] = {}
PER_MINUTE = 30


class TooManyRequestsError(DomainError):
    code = "too_many_requests"


def throttle(user_id: int, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    recent = [t for t in _hits.get(user_id, []) if now - t < 60]
    if len(recent) >= PER_MINUTE:
        raise TooManyRequestsError("Слишком много запросов — подождите минуту")
    recent.append(now)
    _hits[user_id] = recent
