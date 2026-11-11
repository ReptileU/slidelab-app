"""Dispatcher, который понимает запросы из виджетов (widget_query) — aiogram 3.31 о них ещё не знает."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from . import service

log = logging.getLogger(__name__)
WIDGET_UPDATES = ["widget_query", "shared_widget_query"]


class WidgetDispatcher(Dispatcher):
    async def feed_update(self, bot: Bot, update: Update, **kwargs: Any) -> Any:
        extra = update.model_extra or {}
        raw = extra.get("widget_query") or extra.get("shared_widget_query")
        if raw:
            try:
                await service.handle_query(self, bot, raw)
            except Exception:
                log.exception("Запрос из карточки не обработан")
            return None
        return await super().feed_update(bot, update, **kwargs)

    def resolve_used_update_types(self, skip_events: set[str] | None = None) -> list[str]:
        return [*super().resolve_used_update_types(skip_events), *WIDGET_UPDATES]
