"""Настройки из .env. Имена переменных совпадают со старым settings.txt — его можно переименовать в .env."""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: SecretStr
    bot_username: str = "slidelab_order_bot"
    admin_id: int | None = None  # владелец: заявки, проверка работ, ответы клиентам
    admin_username: str = "slidelab_uz"
    # Дополнительно: супергруппа с темами для команды менеджеров (тема на клиента)
    managers_chat_id: int | None = None
    manager_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    webhook_secret: SecretStr | None = None
    webhook_url: str | None = None  # пусто — long polling
    bot_port: int = 8080

    # --- Mini App ---
    webapp_url: str = Field(
        default="https://reptileu.github.io/slidelab-app/",
        validation_alias=AliasChoices("WEBAPP_URL", "MINIAPP_URL"),
    )
    # true — старая витрина index.html (кнопка у клавиатуры + sendData), false — новая Mini App
    legacy_webapp: bool = True
    api_cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    api_port: int = 8010
    dev_tg_id: int | None = None  # только для разработки в браузере без Telegram
    init_data_ttl: int = 24 * 60 * 60

    # --- Хранилище ---
    # Сервер: PostgreSQL. Домашний компьютер: sqlite+aiosqlite:///data/slidelab.db
    database_url: str = "postgresql+asyncpg://slidelab:slidelab@localhost:5433/slidelab"
    redis_url: str | None = None  # пусто — состояние диалогов в памяти (сбрасывается при перезапуске)
    # Папка конвейера: orders/<номер>/brief.json, status.json, review/… — её читает сессия Claude
    work_dir: Path = Path("orders")
    # Посты канала (posts/*.txt), картинки (media/), портфолио (portfolio/)
    content_dir: Path = Path("content")

    # --- Оплата ---
    pay_uzum: str = ""
    pay_payme: str = ""
    pay_zoomrad: str = ""
    pay_name: str = ""
    stars: bool = True  # оплата звёздами Telegram
    credit_days: int = 3  # сколько дней после сдачи заказ можно засчитать в пакет (0 — выключить)
    # Подарок Telegram за пакет: «эмодзи:звёзды», пусто — без подарка
    gift_week: str = "🧸:15"
    gift_month: str = "🌹:25"
    gift_vip: str = "🏆:100"
    gift_until: date = date(2026, 11, 30)

    # --- Канал ---
    channel_url: str = "https://t.me/slidelab_uz"
    post_channel: str = ""  # @канал для публикации постов; пусто — из channel_url
    post_bot_token: SecretStr | None = None  # отдельный бот для публикации (необязательно)

    # --- Сторож заказов ---
    stuck_hours: float = 3

    @field_validator("manager_ids", "api_cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        # В .env списки пишутся через запятую: MANAGER_IDS=1,2,3
        if isinstance(value, str):
            return [x.strip() for x in value.split(",") if x.strip()]
        return value

    @field_validator(
        "admin_id",
        "managers_chat_id",
        "dev_tg_id",
        "redis_url",
        "post_bot_token",
        "webhook_url",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def pay_cards(self) -> list[tuple[str, str]]:
        cards = (("Uzum Bank", self.pay_uzum), ("Payme", self.pay_payme), ("Zoomrad", self.pay_zoomrad))
        return [(label, number.strip()) for label, number in cards if number.strip()]

    @property
    def staff_ids(self) -> set[int]:
        """Кто может пользоваться кнопками менеджера."""
        return set(self.manager_ids) | ({self.admin_id} if self.admin_id else set())

    @property
    def staff_chat_id(self) -> int | None:
        """Куда идут заявки и вопросы: супергруппа менеджеров или личка владельца."""
        return self.managers_chat_id or self.admin_id

    @property
    def channel(self) -> str:
        if self.post_channel:
            return self.post_channel
        url = self.channel_url.rstrip("/")
        if "t.me/" in url and not url.lower().endswith("bot"):
            return "@" + url.split("/")[-1]
        return ""

    @property
    def gifts(self) -> dict[str, str]:
        return {"week": self.gift_week, "month": self.gift_month, "vip": self.gift_vip}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # bot_token берётся из окружения
