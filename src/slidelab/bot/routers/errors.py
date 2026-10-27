"""Ошибки бизнес-правил превращаются в понятный ответ, остальные — в лог и общий ответ."""

import logging

from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

from slidelab.core.enums import Lang
from slidelab.core.errors import DomainError
from slidelab.core.i18n import t

log = logging.getLogger(__name__)
router = Router(name="errors")


@router.error(ExceptionTypeFilter(DomainError))
async def on_domain_error(event: ErrorEvent, lang: Lang | None = None, is_manager: bool = False) -> None:
    # Менеджеру — причина как есть, клиенту — общий текст (детали в логах)
    text = str(event.exception) if is_manager else t(lang, "error")
    await _answer(event, text)


@router.error()
async def on_error(event: ErrorEvent, lang: Lang | None = None) -> None:
    log.error("Необработанная ошибка", exc_info=event.exception)
    await _answer(event, t(lang, "error"))


async def _answer(event: ErrorEvent, text: str) -> None:
    update = event.update
    if update.callback_query is not None:
        await update.callback_query.answer(text[:200], show_alert=True)
    elif update.message is not None:
        await update.message.answer(text)
