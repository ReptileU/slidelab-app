from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from slidelab.core.enums import Lang
from slidelab.core.i18n import TEXTS, t
from slidelab.telegram.premium import EmojiStore, PremiumEmojiMiddleware, render, strip


def test_marks_never_leak_without_premium():
    for lang in Lang:
        for key in TEXTS[lang]:
            assert "⟦" not in strip(TEXTS[lang][key]), key


def test_render_premium_and_fallback():
    marks = {"logo": {"id": "123", "alt": "💎"}}
    assert render("⟦logo⟧<b>X</b>", marks, True) == '<tg-emoji emoji-id="123">💎</tg-emoji> <b>X</b>'
    assert render("⟦logo⟧<b>X</b>", marks, False) == "<b>X</b>"
    assert render("⟦gift|🎁⟧До", {}, True) == "🎁 До"


def test_middleware_private_chat(tmp_path):
    store = EmojiStore(tmp_path / "emoji.json")
    store.set("marks", "logo", "111", "💎")
    store.set("buttons", "btn_new", "222", "➕")
    mw = PremiumEmojiMiddleware(store)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(Lang.RU, "btn_new"))]])
    m = mw._apply(SendMessage(chat_id=5, text=t(Lang.RU, "welcome_back"), reply_markup=kb))
    assert m.text.startswith('<tg-emoji emoji-id="111">')
    assert m.reply_markup.keyboard[0][0].icon_custom_emoji_id == "222"
    # канал/группа: метки убираются, премиум не ставится
    m2 = mw._apply(SendMessage(chat_id=-100123, text=t(Lang.RU, "welcome_back")))
    assert "tg-emoji" not in m2.text and "⟦" not in m2.text


def test_inline_buttons(tmp_path):
    store = EmojiStore(tmp_path / "emoji.json")
    store.set("buttons", "btn_pay", "333", "💳")
    mw = PremiumEmojiMiddleware(store)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(Lang.UZ, "btn_pay"), callback_data="x")]])
    m = mw._apply(SendMessage(chat_id=7, text="hi", reply_markup=kb))
    assert m.reply_markup.inline_keyboard[0][0].icon_custom_emoji_id == "333"
