"""Повторяет все ветки price() из старого index.html."""

import pytest

from slidelab.core.enums import Deadline, PaidFrom, PlanCode, SlideTier
from slidelab.core.services.pricing import (
    PackageBalance,
    PriceRules,
    PricingError,
    QuoteRequest,
    quote,
)

RULES = PriceRules(
    base={SlideTier.S10: 19_000, SlideTier.S20: 29_000, SlideTier.S30: 39_000},
    urgent_pct=50,
    extra_text=5_000,
    extra_notes=5_000,
    first_order_s10=9_900,
)
N, U = Deadline.NORMAL, Deadline.URGENT


def pkg(left: int, plan: PlanCode = PlanCode.MONTH) -> PackageBalance:
    return PackageBalance(plan=plan, left=left, notes_free=plan is PlanCode.VIP)


@pytest.mark.parametrize(
    ("slides", "deadline", "text", "notes", "first", "expected"),
    [
        (SlideTier.S10, N, False, False, False, 19_000),
        (SlideTier.S20, N, False, False, False, 29_000),
        (SlideTier.S30, N, False, False, False, 39_000),
        (SlideTier.S10, N, False, False, True, 9_900),  # первый заказ «Мини»
        (SlideTier.S20, N, False, False, True, 29_000),  # скидка только на «Мини»
        (SlideTier.S10, U, False, False, False, 28_500),
        (SlideTier.S10, U, False, False, True, 14_850),  # срочность от сниженной цены
        (SlideTier.S20, U, False, False, False, 43_500),
        (SlideTier.S20, N, True, False, False, 34_000),
        (SlideTier.S20, N, True, True, False, 39_000),
        (SlideTier.S20, U, True, True, False, 53_500),  # доплаты не умножаются на срочность
        (SlideTier.S30, Deadline.RELAXED, False, True, False, 44_000),
    ],
)
def test_cash_price(slides: SlideTier, deadline: Deadline, text: bool, notes: bool, first: bool, expected: int) -> None:
    q = quote(QuoteRequest(slides, deadline, text, notes), RULES, first_order=first)
    assert q.price == expected
    assert q.paid_from is PaidFrom.CASH
    assert q.package_cost == 0
    assert q.first_order_discount is (first and slides is SlideTier.S10)


def test_urgent_not_allowed_for_30_slides() -> None:
    with pytest.raises(PricingError):
        quote(QuoteRequest(SlideTier.S30, U), RULES)


@pytest.mark.parametrize(
    ("slides", "deadline", "text", "notes", "plan", "expected"),
    [
        (SlideTier.S20, N, False, False, PlanCode.MONTH, 0),
        (SlideTier.S20, U, False, False, PlanCode.MONTH, 14_500),  # 50% от обычной базы
        (SlideTier.S10, U, False, False, PlanCode.MONTH, 9_500),
        (SlideTier.S20, N, True, False, PlanCode.MONTH, 5_000),
        (SlideTier.S20, N, False, True, PlanCode.MONTH, 5_000),
        (SlideTier.S20, N, False, True, PlanCode.VIP, 0),  # у VIP конспект бесплатно
        (SlideTier.S20, N, True, True, PlanCode.VIP, 5_000),
    ],
)
def test_package_price(
    slides: SlideTier, deadline: Deadline, text: bool, notes: bool, plan: PlanCode, expected: int
) -> None:
    q = quote(QuoteRequest(slides, deadline, text, notes), RULES, package=pkg(3, plan))
    assert q.price == expected
    assert q.paid_from is PaidFrom.PACKAGE
    assert q.package_cost == 1
    assert q.package_left_after == 2


def test_package_ignores_first_order_discount() -> None:
    q = quote(QuoteRequest(SlideTier.S10, N), RULES, first_order=True, package=pkg(1))
    assert (q.price, q.paid_from, q.first_order_discount) == (0, PaidFrom.PACKAGE, False)


def test_30_slides_cost_two_from_package() -> None:
    q = quote(QuoteRequest(SlideTier.S30, N), RULES, package=pkg(2))
    assert (q.package_cost, q.package_left_after, q.price) == (2, 0, 0)


@pytest.mark.parametrize("left", [0, 1])
def test_not_enough_in_package_falls_back_to_cash(left: int) -> None:
    q = quote(QuoteRequest(SlideTier.S30, N), RULES, package=pkg(left))
    assert (q.paid_from, q.price, q.package_left_after) == (PaidFrom.CASH, 39_000, None)
