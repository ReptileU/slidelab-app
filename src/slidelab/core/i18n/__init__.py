"""Тексты для клиента на ru / uz / en. Ключи во всех языках одинаковые — это проверяет тест."""

from slidelab.core.enums import Lang
from slidelab.core.i18n import en, ru, uz

TEXTS: dict[Lang, dict[str, str]] = {Lang.RU: ru.TEXTS, Lang.UZ: uz.TEXTS, Lang.EN: en.TEXTS}
DEFAULT = Lang.RU


def t(lang: Lang | None, key: str, **kwargs: object) -> str:
    text = TEXTS[lang or DEFAULT].get(key) or TEXTS[DEFAULT][key]
    return text.format(**kwargs) if kwargs else text


def money(amount: int) -> str:
    """29000 → «29 000» (неразрывный пробел, как в старом приложении)."""
    return f"{amount:,}".replace(",", " ")


def guess_lang(language_code: str | None) -> Lang:
    if language_code == "uz":
        return Lang.UZ
    if language_code and not language_code.startswith(("ru", "uk", "be", "kk")):
        return Lang.EN
    return Lang.RU
