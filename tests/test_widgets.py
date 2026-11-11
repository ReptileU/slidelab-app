import zlib

from slidelab.core.enums import Deadline, Lang, SlideTier
from slidelab.telegram.widgets import cards
from slidelab.telegram.widgets.api import HTML_ZLIB_MAX


def test_cards_fit_telegram_limits() -> None:
    for lang in cards.LANGS:
        for html in (cards.order_html(lang), cards.status_html(lang)):
            assert len(zlib.compress(html.encode(), 9)) <= HTML_ZLIB_MAX and "__T__" not in html


def test_parse_order_request() -> None:
    assert cards.parse_order_request("o:2007") == (
        SlideTier.S30,
        Deadline.NORMAL,  # срочно для 21–30 не бывает
        Lang.RU,
        True,
        True,
        True,
    )
    for bad in ("o:3000", "x:1100", "o:11", "o:1a00"):
        assert cards.parse_order_request(bad) is None
