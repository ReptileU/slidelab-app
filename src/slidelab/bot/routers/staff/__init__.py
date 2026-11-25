"""Рабочее место владельца и менеджеров.

Работает в личке владельца с ботом (как раньше) или в супергруппе менеджеров с темами.
Ответ реплаем на сообщение со строкой «ID: …» уходит клиенту.

Разложено по файлам: cards (кнопки карточки заказа), reports (/stats, /users…), chat (ответы клиентам),
tools (/emoji, /demo, /logo). Фильтр «только команда» стоит на общем роутере и действует на все части.
"""

from aiogram import Router

from slidelab.bot.routers.staff import cards, chat, reports, tools
from slidelab.bot.routers.staff.common import FromStaff
from slidelab.bot.routers.staff.reports import cmd_users

__all__ = ["cmd_users", "router"]

router = Router(name="staff")
router.message.filter(FromStaff())
router.callback_query.filter(FromStaff())
# порядок как был: ответы клиентам (ловят любой текст без команды) идут после карточек и отчётов
router.include_routers(cards.router, reports.router, chat.router, tools.router)
