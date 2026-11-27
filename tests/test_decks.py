from typing import Any

import pytest
from sqlalchemy import select

from slidelab.core.models import CreditsLedger, User
from slidelab.core.services import credits as cr
from test_api import auth
from test_api import env as _api_env  # noqa: F401  фикстура клиента API из test_api


@pytest.fixture
def api_env(_api_env: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    return _api_env


def slide(sid: str, text: str = "Текст", **extra: Any) -> dict[str, Any]:
    return {
        "id": sid,
        "layout": "story",
        "elements": [
            {
                "id": f"{sid}-t",
                "type": "text",
                "role": "body",
                "box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.3},
                "text": text,
            }
        ],
        **extra,
    }


async def make_deck(c: Any) -> dict[str, Any]:
    r = await c.post("/api/decks", json={"title": "Аральское море"}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_blank_and_list(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    deck = await make_deck(c)
    assert deck["version"] == 1 and deck["lang"] == "ru" and deck["slides"] == 1
    cover = deck["body"]["slides"][0]
    assert cover["layout"] == "cover" and cover["elements"][0]["text"] == "Аральское море"

    r = await c.get("/api/decks", headers=auth())
    assert [d["id"] for d in r.json()] == [deck["id"]]
    # чужую не видно
    assert (await c.get(f"/api/decks/{deck['id']}", headers=auth(999))).status_code == 404
    assert (await c.get("/api/decks", headers=auth(999))).json() == []


async def test_save_insert_reorder_delete_slides(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    deck = await make_deck(c)
    did, cover_id = deck["id"], deck["body"]["slides"][0]["id"]

    r = await c.post(f"/api/decks/{did}/slides", json={"version": 1, "slide": slide("a")}, headers=auth())
    assert r.status_code == 201 and r.json()["version"] == 2
    r = await c.post(
        f"/api/decks/{did}/slides", json={"version": 2, "slide": slide("b"), "after": cover_id}, headers=auth()
    )
    assert r.json()["version"] == 3

    chart = {
        "id": "a-c", "type": "chart", "box": {"x": 0.1, "y": 0.5, "w": 0.8, "h": 0.4},
        "chart": {"kind": "bar", "labels": ["1960", "2020"], "series": [{"name": "км²", "values": [68, 4]}]},
        "anim": {"preset": "grow", "trigger": "click"},
    }  # fmt: skip
    a = slide("a", "Площадь моря")
    a["elements"].append(chart)
    r = await c.put(f"/api/decks/{did}/slides/a", json={"version": 3, "slide": a}, headers=auth())
    assert r.status_code == 200 and r.json()["version"] == 4

    body = (await c.get(f"/api/decks/{did}", headers=auth())).json()["body"]
    assert [s["id"] for s in body["slides"]] == [cover_id, "b", "a"]
    assert body["slides"][2]["elements"][1]["chart"]["series"][0]["values"] == [68, 4]

    r = await c.put(f"/api/decks/{did}/order", json={"version": 4, "order": ["a", cover_id, "b"]}, headers=auth())
    assert r.json()["version"] == 5
    r = await c.put(f"/api/decks/{did}/order", json={"version": 5, "order": ["a"]}, headers=auth())
    assert r.status_code == 422

    r = await c.delete(f"/api/decks/{did}/slides/b", params={"version": 5}, headers=auth())
    assert r.json()["version"] == 6
    body = (await c.get(f"/api/decks/{did}", headers=auth())).json()["body"]
    assert [s["id"] for s in body["slides"]] == ["a", cover_id]


async def test_version_conflict(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    did = (await make_deck(c))["id"]
    assert (
        await c.put(f"/api/decks/{did}/slides/a", json={"version": 1, "slide": slide("a")}, headers=auth())
    ).status_code == 200
    # второе окно ещё думает, что версия 1
    r = await c.put(f"/api/decks/{did}/slides/a", json={"version": 1, "slide": slide("a", "другое")}, headers=auth())
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"


async def test_invalid_slides_rejected(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    did = (await make_deck(c))["id"]
    bad = [
        {**slide("a"), "layout": "nope"},
        {**slide("a"), "script": "alert(1)"},  # лишние поля не пропускаем
        slide("a", "x" * 3001),
        {**slide("a"), "elements": [{**slide("a")["elements"][0], "box": {"x": 2, "y": 0, "w": 1, "h": 1}}]},
        {**slide("a"), "elements": [{**slide("a")["elements"][0], "anim": {"preset": "explode"}}]},
    ]
    for s in bad:
        r = await c.put(f"/api/decks/{did}/slides/a", json={"version": 1, "slide": s}, headers=auth())
        assert r.status_code == 422, s
    r = await c.put(f"/api/decks/{did}/slides/b", json={"version": 1, "slide": slide("a")}, headers=auth())
    assert r.status_code == 409  # id в адресе и в теле разный


async def test_meta_theme_and_delete(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    did = (await make_deck(c))["id"]
    theme = {"palette": {"accent": "#00AAFF"}, "fonts": {"head": "Montserrat"}}
    r = await c.patch(
        f"/api/decks/{did}", json={"version": 1, "title": "Арал", "lang": "uz", "theme": theme}, headers=auth()
    )
    assert r.status_code == 200
    deck = (await c.get(f"/api/decks/{did}", headers=auth())).json()
    assert deck["title"] == "Арал" and deck["lang"] == "uz"
    assert deck["body"]["theme"]["palette"]["accent"] == "#00AAFF"
    assert deck["body"]["theme"]["palette"]["bg"] == "#0E1116"  # остальное — по умолчанию

    assert (await c.delete(f"/api/decks/{did}", headers=auth(999))).status_code == 404
    assert (await c.delete(f"/api/decks/{did}", headers=auth())).status_code == 204
    assert (await c.get(f"/api/decks/{did}", headers=auth())).status_code == 404


async def test_credits_endpoint(api_env: dict[str, Any]) -> None:
    c = api_env["client"]
    r = await c.get("/api/credits", headers=auth())
    data = r.json()
    assert data["balance"] == cr.WELCOME and data["daily_cap"] == cr.DAILY_CAP and data["costs"]["draft"] == 10
    assert (await c.get("/api/credits", headers=auth())).json()["balance"] == cr.WELCOME
    async with api_env["sm"]() as s:
        user = (await s.scalars(select(User))).one()
        rows = (await s.scalars(select(CreditsLedger).where(CreditsLedger.user_id == user.id))).all()
        assert [(r.delta, r.reason) for r in rows] == [(cr.WELCOME, "welcome")]
