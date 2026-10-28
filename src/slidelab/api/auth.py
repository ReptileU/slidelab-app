"""Проверка initData Telegram Mini App.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode


class InitDataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TgUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    photo_url: str | None


def validate_init_data(init_data: str, bot_token: str, ttl: int, now: float | None = None) -> TgUser:
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as e:
        raise InitDataError("initData не разбирается") from e

    received = data.pop("hash", None)
    if not received:
        raise InitDataError("В initData нет подписи")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataError("Подпись initData не совпадает")

    auth_date = int(data.get("auth_date", "0"))
    if (now if now is not None else time.time()) - auth_date > ttl:
        raise InitDataError("initData устарела — откройте приложение заново")

    try:
        raw: dict[str, Any] = json.loads(data["user"])
        return TgUser(
            id=int(raw["id"]),
            first_name=str(raw.get("first_name", "")),
            last_name=raw.get("last_name"),
            username=raw.get("username"),
            language_code=raw.get("language_code"),
            photo_url=raw.get("photo_url"),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise InitDataError("В initData нет пользователя") from e


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Подписать initData так же, как Telegram. Нужна тестам и локальной разработке."""
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signed = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signed})
