"""Постоянная ссылка на Mini App при временном адресе.

Mini App работает с компьютера через временную ссылку cloudflared, которая меняется при каждом запуске.
Кнопка «Открыть» (Main App в BotFather) ведёт на постоянную страницу GitHub Pages; эта страница читает
app.json из репозитория и переходит по актуальной ссылке. Здесь бот записывает app.json через GitHub API.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime

import aiohttp

from slidelab.config import Settings

log = logging.getLogger(__name__)
API = "https://api.github.com"
PATH = "app.json"


def payload(url: str) -> str:
    return json.dumps({"url": url, "updated": datetime.now(UTC).isoformat(timespec="seconds")}, indent=1) + "\n"


async def publish(settings: Settings) -> bool:
    """Записать текущую ссылку Mini App в app.json. True — записано или уже актуально."""
    url = settings.webapp_url.strip()
    if settings.github_token is None or settings.legacy_webapp or not url.startswith("https://"):
        return False
    if "github.io" in url:  # ссылка и так постоянная
        return False
    token = settings.github_token.get_secret_value().strip()
    if not token:
        return False
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "slidelab-bot",
    }
    target = f"{API}/repos/{settings.github_repo}/contents/{PATH}"
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as http:
            sha = None
            async with http.get(target, params={"ref": settings.github_branch}) as r:
                if r.status == 200:
                    data = await r.json()
                    sha = data.get("sha")
                    try:
                        current = json.loads(base64.b64decode(data.get("content", "")).decode())
                        if current.get("url") == url:
                            log.info("app.json уже указывает на %s", url)
                            return True
                    except ValueError:
                        pass
                elif r.status != 404:
                    log.warning("GitHub: не прочитал app.json (%s)", r.status)
                    return False
            body = {
                "message": "Ссылка на Mini App",
                "content": base64.b64encode(payload(url).encode()).decode(),
                "branch": settings.github_branch,
            }
            if sha:
                body["sha"] = sha
            async with http.put(target, json=body) as r:
                if r.status in (200, 201):
                    log.info("app.json → %s", url)
                    return True
                log.warning("GitHub: не записал app.json (%s): %s", r.status, (await r.text())[:200])
    except (aiohttp.ClientError, TimeoutError) as e:
        log.warning("GitHub недоступен: %s", e)
    return False
