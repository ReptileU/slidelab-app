"""Настройки из .env. Имена переменных совпадают со старым settings.txt — его можно переименовать в .env."""

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def normalize_db_url(url: str) -> str:
    """Адрес от облачной базы (Neon, Render: postgres://… ?sslmode=require) → вид для asyncpg."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+asyncpg://") and "?" in url:
        base, _, query = url.partition("?")
        params = []
        for part in query.split("&"):
            name, _, value = part.partition("=")
            if name == "sslmode":
                params.append(f"ssl={value}")
            elif name in ("channel_binding", "options"):
                continue  # asyncpg их не знает
            elif part:
                params.append(part)
        url = base + ("?" + "&".join(params) if params else "")
    return url


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
    # Облако: ключ, по которому сессия Claude берёт заказы и сдаёт работу через /pipeline (пусто — выключено)
    pipeline_key: SecretStr | None = None
    bot_port: int = 8080

    # --- Mini App ---
    webapp_url: str = Field(
        default="https://reptileu.github.io/slidelab-app/",
        validation_alias=AliasChoices("WEBAPP_URL", "MINIAPP_URL"),
    )
    # true — старая витрина index.html (кнопка у клавиатуры + sendData), false — новая Mini App
    legacy_webapp: bool = True
    api_cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    menu_button: str = "SlideLab"  # кнопка меню слева от поля ввода (открывает Mini App)
    dev_tg_id: int | None = None  # только для разработки в браузере без Telegram
    init_data_ttl: int = 24 * 60 * 60
    # Кнопка «Открыть» (Main App в BotFather) ведёт на постоянную страницу GitHub Pages, а она — на текущую
    # временную ссылку. Бот при запуске записывает эту ссылку в app.json репозитория. Пусто — не записывать.
    github_token: SecretStr | None = None
    github_repo: str = "ReptileU/slidelab-app"
    github_branch: str = "main"

    # --- Хранилище ---
    # Сервер: PostgreSQL. Домашний компьютер: sqlite+aiosqlite:///data/slidelab.db
    database_url: str = "postgresql+asyncpg://slidelab:slidelab@localhost:5433/slidelab"
    redis_url: str | None = None  # пусто — состояние диалогов в памяти (сбрасывается при перезапуске)
    # Папка конвейера: orders/<номер>/brief.json, status.json, review/… — её читает сессия Claude
    work_dir: Path = Path("orders")
    # Посты канала (posts/*.txt), картинки (media/), портфолио (portfolio/)
    content_dir: Path = Path("content")
    # Служебные файлы бота (карточки-виджеты: data/widgets.json)
    data_dir: Path = Path("data")
    # Картинки конструктора презентаций хранит Telegram: бот кладёт их файлами в этот закрытый канал
    # (бот — администратор канала). Пусто — в чат команды без звука. Позже — R2 (core/services/deck_assets.py)
    assets_chat_id: int | None = None
    # Помощник конструктора: поиск видео (бесплатный ключ Google Cloud с YouTube Data API). Пусто — без видео
    youtube_api_key: SecretStr | None = None

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

    @field_validator("database_url", mode="after")
    @classmethod
    def _db_url(cls, value: str) -> str:
        return normalize_db_url(value)

    @field_validator("bot_username", mode="before")
    @classmethod
    def _bare_username(cls, value: object) -> object:
        # В Render могли вписать ссылку: https://t.me/SlideLabTestbot или @SlideLabTestbot — нужен голый username
        if isinstance(value, str):
            v = value.strip().rstrip("/")
            v = re.sub(r"^(https?://)?(www\.)?(t\.me|telegram\.me)/", "", v)
            return v.lstrip("@")
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
    def deck_assets_chat_id(self) -> int | None:
        return self.assets_chat_id or self.staff_chat_id

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
