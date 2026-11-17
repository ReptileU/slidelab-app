"""Расчёт цены заказа. Перенос `price()` из старого index.html — без обращений к БД.

Правила:
1. База по числу слайдов; первая презентация (до 15 слайдов) нового клиента — по сниженной цене.
2. Срочно: +urgent_pct %, только до 20 слайдов.
3. Текст слайдов входит в цену. Доплачиваются только срочность и речь для выступления (у VIP речь бесплатно).
4. Если в пакете хватает остатка, база не берётся: доплачиваются только срочность (от обычной базы) и речь.
5. Есть оплаченная презентация от отменённого заказа — база не берётся (больше слайдов — только разница),
   доплачиваются срочность и речь. Она идёт в зачёт раньше пакета: у пакета есть срок, у неё нет.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from slidelab.core.enums import Deadline, PaidFrom, PlanCode, SlideTier


class PricingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PriceRules:
    base: Mapping[SlideTier, int]
    urgent_pct: int
    extra_text: int
    extra_notes: int
    first_order_s10: int


@dataclass(frozen=True, slots=True)
class PackageBalance:
    plan: PlanCode
    left: int
    notes_free: bool


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    slides: SlideTier
    deadline: Deadline
    extra_text: bool = False
    extra_notes: bool = False


@dataclass(frozen=True, slots=True)
class Quote:
    price: int  # к оплате деньгами
    paid_from: PaidFrom
    package_cost: int  # сколько презентаций спишется из пакета (0 — не из пакета)
    package_left_after: int | None
    first_order_discount: bool
    voucher: bool = False  # база оплачена отменённым заказом


def package_cost(slides: SlideTier) -> int:
    """21–30 слайдов списывают из пакета две презентации."""
    return 2 if slides is SlideTier.S30 else 1


def to_stars(amount_uzs: int, uzs_per_star: int) -> int:
    """Сумы → звёзды Telegram: вверх до кратного 5 (как в прежнем боте)."""
    step = uzs_per_star * 5
    return max(5, -(-amount_uzs // step) * 5)


def percent_of(amount: int, pct: int) -> int:
    """Процент с округлением половины вверх (как Math.round в старом фронте)."""
    return (amount * pct + 50) // 100


def validate(req: QuoteRequest) -> None:
    if req.deadline is Deadline.URGENT and req.slides is SlideTier.S30:
        raise PricingError("Срочно делаем только до 20 слайдов")


def quote(
    req: QuoteRequest,
    rules: PriceRules,
    *,
    first_order: bool = False,
    package: PackageBalance | None = None,
    voucher: SlideTier | None = None,
) -> Quote:
    validate(req)
    base = rules.base[req.slides]
    cost = package_cost(req.slides)

    if voucher is not None:
        price = max(0, base - rules.base[voucher])  # больше слайдов, чем в отменённом, — только разница
        if req.deadline is Deadline.URGENT:
            price += percent_of(base, rules.urgent_pct)
        if req.extra_notes:
            price += rules.extra_notes
        return Quote(
            price=price,
            paid_from=PaidFrom.CASH,
            package_cost=0,
            package_left_after=None,
            first_order_discount=False,
            voucher=True,
        )

    if package is not None and package.left >= cost:
        price = 0
        if req.deadline is Deadline.URGENT:
            price += percent_of(base, rules.urgent_pct)
        if req.extra_notes and not package.notes_free:
            price += rules.extra_notes
        return Quote(
            price=price,
            paid_from=PaidFrom.PACKAGE,
            package_cost=cost,
            package_left_after=package.left - cost,
            first_order_discount=False,
        )

    discount = first_order and req.slides is SlideTier.S10
    price = rules.first_order_s10 if discount else base
    if req.deadline is Deadline.URGENT:
        price += percent_of(price, rules.urgent_pct)
    if req.extra_notes:
        price += rules.extra_notes
    return Quote(
        price=price,
        paid_from=PaidFrom.CASH,
        package_cost=0,
        package_left_after=None,
        first_order_discount=discount,
    )
