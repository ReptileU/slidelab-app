import base64
import json
import string
from datetime import UTC, datetime

import pytest

from slidelab.core.enums import Deadline, Design, Lang, OrderStatus, PlanCode, SlideTier
from slidelab.core.i18n import TEXTS, money, t
from slidelab.core.models import Order, UserPackage
from slidelab.telegram import legacy

# --- переводы ---------------------------------------------------------------


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.mark.parametrize("lang", [Lang.UZ, Lang.EN])
def test_all_languages_have_same_keys_and_placeholders(lang: Lang) -> None:
    ru = TEXTS[Lang.RU]
    other = TEXTS[lang]
    assert set(other) == set(ru)
    for key, text in ru.items():
        assert _placeholders(other[key]) == _placeholders(text), key


def test_t_formats_and_falls_back_to_russian() -> None:
    assert t(Lang.EN, "files_attached", id=7) == "Added to order #7."
    assert t(None, "files_attached", id=7) == "Добавил к заказу #7."
    assert money(145000) == "145 000"


# --- заявки старой витрины ----------------------------------------------------


def start_code_like_js(
    slides: str, deadline: str, plang: str, design: str, text: bool, notes: bool, lang: str, topic: str
) -> str:
    """Тот же алгоритм, что startCode() в index.html."""
    code = "o" + {"s10": "1", "s20": "2", "s30": "3"}[slides] + {"d1": "1", "d2": "2", "d3": "3"}[deadline]
    code += {"ru": "r", "uz": "u", "en": "e"}[plang] + ("w" if design == "own" else "o")
    code += ("1" if text else "0") + ("1" if notes else "0") + {"uz": "u", "en": "e"}.get(lang, "r")
    raw = topic.encode()[: (64 - len(code)) * 6 // 8]
    return code + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_start_code_roundtrip() -> None:
    code = start_code_like_js("s20", "d1", "uz", "own", True, False, "uz", "Iqtisodiyot")
    parsed = legacy.parse_start_code(code)
    assert parsed is not None
    d = parsed.draft
    assert (d.slides, d.deadline, d.pres_lang, d.design) == (
        SlideTier.S20,
        Deadline.URGENT,
        Lang.UZ,
        Design.OWN,
    )
    assert (d.extra_text, d.extra_notes, d.topic, parsed.ui_lang) == (True, False, "Iqtisodiyot", Lang.UZ)


def test_start_code_with_cyrillic_topic_is_cut_safely() -> None:
    code = start_code_like_js("s10", "d2", "ru", "ours", False, False, "ru", "Экономика Японии после 1990 года и далее")
    assert len(code) <= 64
    parsed = legacy.parse_start_code(code)
    assert parsed is not None and parsed.draft.topic.startswith("Экономика Японии")


@pytest.mark.parametrize("bad", ["", "ask", "sub_week", "o9", "o12rx00r", "oXYZ12345"])
def test_not_a_start_code(bad: str) -> None:
    assert legacy.parse_start_code(bad) is None


def test_web_app_data_order() -> None:
    raw = json.dumps(
        {
            "v": 1,
            "lang": "en",
            "topic": "Japan after 1990",
            "slides": "s30",
            "deadline": "d3",
            "plang": "en",
            "design": "own",
            "text": False,
            "notes": True,
            "contact": "+998 90 000 00 00",
            "comment": "teacher wants charts",
            "sources": "https://example.com",
            "srcfiles": True,
            "style": "Минимализм",
            "dlink": "https://canva.com/x",
        }
    )
    action = legacy.parse_web_app_data(raw)
    assert isinstance(action, legacy.LegacyOrder)
    d = action.draft
    assert (d.slides, d.deadline, d.design, d.template_url) == (
        SlideTier.S30,
        Deadline.RELAXED,
        Design.OWN,
        "https://canva.com/x",
    )
    assert d.comment == "teacher wants charts" and action.style_name == "Минимализм"
    assert d.has_source_files and d.extra_notes and not d.need_humor and action.ui_lang is Lang.EN


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"type":"sub","plan":"vip","lang":"ru"}', legacy.LegacyPlan(PlanCode.VIP)),
        ('{"type":"edit","lang":"ru","id":12,"text":"слайд 3"}', legacy.LegacyRevision(12, "слайд 3")),
        ('{"type":"q","lang":"ru","text":"Когда будет?"}', legacy.LegacyQuestion("Когда будет?")),
        ('{"type":"hide","id":"all"}', legacy.LegacyHide(None)),
        ('{"type":"hide","id":"7"}', legacy.LegacyHide(7)),
        ('{"type":"get","id":"7","fmt":"pdf"}', legacy.LegacyGetFormat(7, "pdf")),
        ('{"type":"get","id":"7","fmt":"exe"}', None),
        ('{"type":"sub","plan":"unknown"}', None),
        ("not json", None),
        ('{"v":1,"topic":"x"}', None),
    ],
)
def test_web_app_data_other(raw: str, expected: object) -> None:
    assert legacy.parse_web_app_data(raw) == expected


def test_webapp_url_matches_old_frontend_format() -> None:
    order = Order(id=5, topic="Тема", slides=SlideTier.S20, status=OrderStatus.AWAITING_PAYMENT, price=29000)
    done = Order(
        id=4,
        topic="Готовая",
        slides=SlideTier.S10,
        status=OrderStatus.DONE,
        price=19000,
        deliver_dir="4/sent_deck",
        deliver_files=["deck.pptx", "deck.pdf", "notes.docx"],
        deliver_links={"view": "https://canva.com/v/view"},
    )
    package = UserPackage(plan_code=PlanCode.MONTH, left=3, total=4, expires_at=datetime(2026, 11, 25, tzinfo=UTC))
    url = legacy.webapp_url(
        "https://x.github.io/app/",
        lang=Lang.RU,
        orders=[order, done],
        package=package,
        first_order_price=None,
        tab="order",
    )
    from urllib.parse import parse_qs, urlparse

    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["lang"] == "ru" and q["tab"] == "order" and "n" not in q
    assert q["s"] == "month.3.4.2026-11-25"
    rows = json.loads(base64.urlsafe_b64decode(q["o"] + "=" * (-len(q["o"]) % 4)))
    assert rows == [
        [5, "Тема", "s20", "cover", 29000],
        [4, "Готовая", "s10", "done", 19000, "", 1, "https://canva.com/v/view", "pptx,pdf,gslides,canva"],
    ]


def test_start_payload_hide_and_get() -> None:
    assert legacy.parse_start_payload("hide_all") == legacy.LegacyHide(None)
    assert legacy.parse_start_payload("hide_12") == legacy.LegacyHide(12)
    assert legacy.parse_start_payload("get_12_canva") == legacy.LegacyGetFormat(12, "canva")
    assert legacy.parse_start_payload("get_12") is None


def test_start_code_humor_flag() -> None:
    code = start_code_like_js("s10", "d2", "ru", "ours", False, False, "ru", "Мемы и экономика")
    humor = code[:7] + code[7].upper() + code[8:]
    parsed = legacy.parse_start_code(humor)
    assert parsed is not None and parsed.draft.need_humor and parsed.ui_lang is Lang.RU
