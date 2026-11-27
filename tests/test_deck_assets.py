import base64
import io
from typing import Any

import pytest
from PIL import Image

from slidelab.core.services import deck_assets as da
from test_api import MANAGERS_CHAT, auth
from test_api import env as _api_env  # noqa: F401  фикстура клиента API из test_api


@pytest.fixture
def api_env(_api_env: dict[str, Any]) -> dict[str, Any]:  # noqa: F811
    da.CACHE.items.clear()
    da.CACHE.size = 0
    return _api_env


def png(w: int, h: int, mode: str = "RGB") -> str:
    buf = io.BytesIO()
    Image.new(mode, (w, h), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def make_deck(c: Any, tg: int | None = None) -> int:
    r = await c.post("/api/decks", json={"title": "Арал"}, headers=auth(tg) if tg else auth())
    return int(r.json()["id"])


def test_process_image_shrinks_and_keeps_alpha() -> None:
    raw = base64.b64decode(png(4000, 1000, "RGBA").split(",", 1)[1])
    out = da.process_image(raw)
    assert (out.width, out.height) == (2000, 500)
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.format == "WEBP" and img.mode == "RGBA"
    with pytest.raises(da.AssetError):
        da.process_image(b"GIF89a" + b"0" * 100)
    with pytest.raises(da.AssetError):
        da.process_image(b"\x00" * (da.MAX_UPLOAD + 1))


async def test_upload_list_show_delete(api_env: dict[str, Any]) -> None:
    c, tg = api_env["client"], api_env["tg"]
    did = await make_deck(c)
    r = await c.post(f"/api/decks/{did}/assets", json={"data": png(3000, 2000), "kind": "logo"}, headers=auth())
    assert r.status_code == 201, r.text
    asset = r.json()
    assert (asset["width"], asset["height"], asset["kind"]) == (2000, 1333, "logo")

    # файл ушёл документом в чат команды без звука, в базе — только ключ
    send = tg.of("SendDocument")[-1]
    assert send.chat_id == MANAGERS_CHAT and send.disable_notification is True

    # картинка открывается по подписанной ссылке без initData (из кэша — без похода в Telegram)
    calls = len(tg.calls)
    r = await c.get(asset["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content[:4] == b"RIFF"
    assert len(tg.calls) == calls

    # после перезапуска сервера кэша нет — скачиваем из Telegram
    da.CACHE.items.clear()
    r = await c.get(asset["url"])
    assert r.status_code == 200 and tg.of("GetFile")

    bad = asset["url"].replace("sig=", "sig=0")
    assert (await c.get(bad)).status_code == 403

    listed = (await c.get(f"/api/decks/{did}/assets", headers=auth())).json()
    assert [a["id"] for a in listed] == [asset["id"]]
    assert (await c.get(f"/api/decks/{did}/assets", headers=auth(999))).status_code == 404

    assert (await c.delete(f"/api/decks/{did}/assets/{asset['id']}", headers=auth())).status_code == 204
    assert (await c.get(asset["url"])).status_code == 404


async def test_upload_rules(api_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    c = api_env["client"]
    did = await make_deck(c)
    other = await make_deck(c, tg=999)
    assert (await c.post(f"/api/decks/{other}/assets", json={"data": png(10, 10)}, headers=auth())).status_code == 404
    r = await c.post(f"/api/decks/{did}/assets", json={"data": "не картинка"}, headers=auth())
    assert r.status_code == 422 and r.json()["code"] == "asset_invalid"

    monkeypatch.setattr(da, "MAX_ASSETS", 2)
    for _ in range(2):
        assert (await c.post(f"/api/decks/{did}/assets", json={"data": png(10, 10)}, headers=auth())).status_code == 201
    r = await c.post(f"/api/decks/{did}/assets", json={"data": png(10, 10)}, headers=auth())
    assert r.status_code == 409 and r.json()["code"] == "asset_limit"
