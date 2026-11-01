import base64
import json

from aiohttp import web
from pydantic import SecretStr

from slidelab.config import Settings
from slidelab.telegram import app_link


async def test_publish_roundtrip(monkeypatch, unused_tcp_port):
    store: dict[str, str] = {}

    async def get(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer t0ken"
        if "content" not in store:
            return web.Response(status=404)
        return web.json_response({"sha": "abc", "content": store["content"]})

    async def put(request: web.Request) -> web.Response:
        body = await request.json()
        if "content" in store:
            assert body["sha"] == "abc"
        store["content"] = body["content"]
        store["puts"] = store.get("puts", "") + "x"
        return web.json_response({}, status=201)

    app = web.Application()
    app.router.add_get("/repos/o/r/contents/app.json", get)
    app.router.add_put("/repos/o/r/contents/app.json", put)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    monkeypatch.setattr(app_link, "API", f"http://127.0.0.1:{unused_tcp_port}")
    try:
        s = Settings(
            bot_token="1:x",
            admin_id=1,
            webapp_url="https://a-b.trycloudflare.com/",
            legacy_webapp=False,
            github_token=SecretStr("t0ken"),
            github_repo="o/r",
        )
        assert await app_link.publish(s)
        assert json.loads(base64.b64decode(store["content"]))["url"] == "https://a-b.trycloudflare.com/"
        assert await app_link.publish(s)  # уже актуально — без второй записи
        assert store["puts"] == "x"
        assert not await app_link.publish(s.model_copy(update={"github_token": None}))
    finally:
        await runner.cleanup()
