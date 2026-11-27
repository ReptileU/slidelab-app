import io
from typing import Any
from urllib.parse import unquote

import pytest
from PIL import Image

from slidelab.core.services import research as rs
from test_api import auth
from test_api import env as _api_env  # noqa: F401  фикстура клиента API из test_api


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


class FakeFetcher:
    """Ответы источников в их настоящем формате (сокращённо)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(url)
        p = params or {}
        if "wikipedia.org/w/api.php" in url and p.get("list") == "search":
            return {"query": {"search": [{"title": "Аральское море"}, {"title": "Амударья"}]}}
        if "/page/summary/" in url:
            name = unquote(url.rsplit("/", 1)[1]).replace("_", " ")
            return {
                "type": "standard",
                "title": name,
                "extract": "Бессточное солёное озеро в Средней Азии. " * 20,
                "content_urls": {"desktop": {"page": f"https://ru.wikipedia.org/wiki/{name}"}},
            }
        if p.get("action") == "parse":
            secs = [
                ("География", 1), ("История", 1), ("Древность", 2), ("Высыхание", 2),
                ("Экология", 1), ("Примечания", 1), ("Литература", 1),
            ]  # fmt: skip
            return {"parse": {"sections": [{"line": n, "toclevel": lvl} for n, lvl in secs]}}
        if "openalex" in url:
            return {
                "results": [
                    {
                        "display_name": "The Aral Sea <i>disaster</i>",
                        "publication_year": 2007,
                        "doi": "https://doi.org/10.1/abc",
                        "cited_by_count": 512,
                        "authorships": [{"author": {"display_name": f"A{i}"}} for i in range(5)],
                        "abstract_inverted_index": {"The": [0], "sea": [1, 3], "shrank,": [2]},
                    }
                ]
            }
        if "commons.wikimedia.org" in url:
            return {
                "query": {
                    "pages": {
                        "2": {"index": 2, "title": "File:Map.svg", "imageinfo": [{"mime": "image/svg+xml"}]},
                        "1": {
                            "index": 1,
                            "title": "File:Aral ships.jpg",
                            "imageinfo": [
                                {
                                    "mime": "image/jpeg",
                                    "url": "https://upload.wikimedia.org/a/Aral_ships.jpg",
                                    "thumburl": "https://upload.wikimedia.org/thumb/a/640px.jpg",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Aral_ships.jpg",
                                    "width": 4000,
                                    "height": 3000,
                                    "extmetadata": {
                                        "Artist": {"value": '<a href="x">Staecker</a>'},
                                        "LicenseShortName": {"value": "CC BY-SA 3.0"},
                                    },
                                }
                            ],
                        },
                    }
                }
            }
        if "worldbank" in url:
            rows = [
                {"date": str(y), "value": v, "country": {"value": "Uzbekistan"}}
                for y, v in [(2022, 35.6e6), (2021, 34.9e6), (2020, None)]
            ]
            return [{"page": 1}, rows]
        if "googleapis.com/youtube" in url:
            return {
                "items": [{"id": {"videoId": "xyz"}, "snippet": {"title": "Арал &amp; люди", "channelTitle": "Doc"}}]
            }
        raise AssertionError(url)

    async def bytes(self, url: str) -> bytes:
        self.calls.append(url)
        return jpeg()


@pytest.fixture
def api_env(_api_env: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    rs._cache.clear()
    rs._hits.clear()
    fetcher = FakeFetcher()
    _api_env["client"]._transport.app.state.research_fetcher = fetcher
    _api_env["fetcher"] = fetcher
    return _api_env


async def test_facts_plan_history(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    facts = (await c.get("/api/research/facts", params={"q": "Аральское море"}, headers=auth())).json()
    assert [f["title"] for f in facts] == ["Аральское море", "Амударья"]
    assert len(facts[0]["text"]) <= 421 and facts[0]["text"].endswith("…")

    plan = (await c.get("/api/research/plan", params={"q": "Аральское море"}, headers=auth())).json()
    assert [(i["title"], i["level"]) for i in plan["items"]] == [
        ("География", 1), ("История", 1), ("Древность", 2), ("Высыхание", 2), ("Экология", 1),
    ]  # fmt: skip
    assert plan["history"] == ["Древность", "Высыхание"]

    # повтор — из кэша, без новых запросов
    before = len(api_env["fetcher"].calls)
    await c.get("/api/research/plan", params={"q": "аральское МОРЕ"}, headers=auth())
    assert len(api_env["fetcher"].calls) == before


async def test_papers_photos_stats(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    paper = (await c.get("/api/research/papers", params={"q": "Aral sea"}, headers=auth())).json()[0]
    assert paper["title"] == "The Aral Sea disaster" and paper["authors"] == "A0, A1, A2 и др."
    assert paper["abstract"] == "The sea shrank, sea" and paper["cited"] == 512

    photos = (await c.get("/api/research/photos", params={"q": "Aral"}, headers=auth())).json()
    assert len(photos) == 1  # svg отброшен
    assert photos[0]["author"] == "Staecker" and photos[0]["license"] == "CC BY-SA 3.0"

    st = (
        await c.get("/api/research/stats", params={"country": "uz", "indicator": "SP.POP.TOTL"}, headers=auth())
    ).json()
    assert st["labels"] == ["2021", "2022"] and st["country"] == "Uzbekistan" and st["label"] == "Население"
    r = await c.get("/api/research/stats", params={"country": "uz", "indicator": "DROP"}, headers=auth())
    assert r.status_code == 502


async def test_videos_only_with_key(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    assert (await c.get("/api/research/sources", headers=auth())).json()["videos"] is False
    assert (await c.get("/api/research/videos", params={"q": "Арал"}, headers=auth())).status_code == 404

    from pydantic import SecretStr

    c._transport.app.state.settings.youtube_api_key = SecretStr("k")
    assert (await c.get("/api/research/sources", headers=auth())).json()["videos"] is True
    v = (await c.get("/api/research/videos", params={"q": "Арал"}, headers=auth())).json()
    assert v == [
        {
            "title": "Арал & люди",
            "channel": "Doc",
            "url": "https://www.youtube.com/watch?v=xyz",
            "thumb": "",
            "published": "",
        }
    ]


async def test_add_found_photo_only_from_wikimedia(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    did = (await c.post("/api/decks", json={"title": "Арал"}, headers=auth())).json()["id"]
    r = await c.post(
        f"/api/research/decks/{did}/photo", json={"url": "https://upload.wikimedia.org/a/x.jpg"}, headers=auth()
    )
    assert r.status_code == 201 and r.json()["width"] == 800
    for bad in ("http://upload.wikimedia.org/x.jpg", "https://evil.example/x.jpg", "https://169.254.169.254/"):
        r = await c.post(f"/api/research/decks/{did}/photo", json={"url": bad}, headers=auth())
        assert r.status_code == 502, bad


async def test_throttle(api_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rs, "PER_MINUTE", 2)
    c = api_env["client"]
    codes = [(await c.get("/api/research/papers", params={"q": "Aral"}, headers=auth())).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
