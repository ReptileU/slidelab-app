"""Приглашения друзей.

Правила (цифры — здесь, в одном месте):
- у каждого клиента своя ссылка t.me/<бот>?start=ref_<код>;
- засчитывается только новый человек: пришёл по ссылке в первые сутки после первого запуска бота
  и ещё ничего не покупал; себя пригласить нельзя; у человека один пригласивший;
- другу — выгода сразу видна: за первую покупку деньгами баллов вдвое больше (обычные 50 + FRIEND_BONUS),
  то есть сразу бронзовый кейс. Второй скидки нет — со скидкой на первую презентацию ничего не путается;
- пригласившему — INVITER_POINTS, когда друг впервые заплатит деньгами (не за регистрацию — иначе накрутят),
  и бонусы за количество оплативших друзей: за третьего — бесплатная презентация (купон),
  за десятого — баллы на золотой кейс (MILESTONES).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from slidelab.core.enums import CouponOrigin, PaymentStatus, PointsReason, SlideTier
from slidelab.core.models import Coupon, Payment, Referral, User
from slidelab.core.models.base import as_utc, utcnow

INVITER_POINTS = 100  # = бронзовый кейс
FRIEND_BONUS = 50  # сверх обычных 50 за первую покупку
# оплативших друзей → бонус: ("coupon", 1) — купон на бесплатную презентацию до 20 слайдов, ("points", N) — баллы
MILESTONES: dict[int, tuple[str, int]] = {3: ("coupon", 1), 10: ("points", 500)}
NEW_WINDOW = timedelta(hours=24)
PREFIX = "ref_"
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def code_for(user_id: int) -> str:
    """Короткий код из внутреннего id (не tg_id): ref_k3."""
    n, out = user_id, ""
    while True:
        n, r = divmod(n, 36)
        out = _ALPHABET[r] + out
        if n == 0:
            return out


def parse_code(code: str) -> int | None:
    try:
        return int(code, 36) if code and len(code) <= 10 else None
    except ValueError:
        return None


@dataclass(slots=True)
class ReferralReward:
    """Что начислено, когда приглашённый друг впервые заплатил."""

    inviter: User
    friend: User
    points: int  # пригласившему, вместе с бонусом за количество
    milestone: int | None = None  # сколько оплативших друзей дало бонус (3, 10)
    friend_bonus: int = 0
    paid_friends: int = 0
    coupon: bool = False  # за этого друга выдан купон на бесплатную презентацию


@dataclass(slots=True)
class FriendRow:
    name: str
    joined_at: datetime
    paid_at: datetime | None
    points: int


@dataclass(slots=True)
class Summary:
    code: str
    friends: list[FriendRow] = field(default_factory=list)
    paid: int = 0
    earned: int = 0


class ReferralService:
    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = utcnow) -> None:
        self.session = session
        self.clock = clock

    async def attach(self, friend: User, code: str) -> Referral | None:
        """Друг открыл бота по ссылке. None — не засчитываем (сам себя, не новый, уже чей-то)."""
        inviter_id = parse_code(code)
        if inviter_id is None or inviter_id == friend.id:
            return None
        inviter = await self.session.get(User, inviter_id)
        if inviter is None:
            return None
        if await self.session.scalar(select(Referral.id).where(Referral.friend_id == friend.id)) is not None:
            return None
        if friend.created_at is not None and self.clock() - as_utc(friend.created_at) > NEW_WINDOW:
            return None
        bought = await self.session.scalar(
            select(Payment.id).where(Payment.user_id == friend.id, Payment.status == PaymentStatus.PAID).limit(1)
        )
        if bought is not None:
            return None
        referral = Referral(inviter_id=inviter.id, friend_id=friend.id)
        self.session.add(referral)
        await self.session.flush()
        return referral

    async def inviter_of(self, friend: User) -> User | None:
        ref = await self.session.scalar(select(Referral).where(Referral.friend_id == friend.id))
        return await self.session.get(User, ref.inviter_id) if ref else None

    async def pending_for(self, friend: User) -> bool:
        """Пришёл по ссылке и ещё не платил — в приложении показываем «×2 баллов за первую покупку»."""
        return (
            await self.session.scalar(
                select(Referral.id).where(Referral.friend_id == friend.id, Referral.paid_at.is_(None))
            )
            is not None
        )

    async def on_paid(self, friend: User, payment_id: int | None) -> ReferralReward | None:
        """Друг впервые заплатил деньгами: баллы обоим. Повторно — ничего."""
        from slidelab.core.services.points import PointsService  # без цикла импортов

        ref = await self.session.scalar(
            select(Referral).where(Referral.friend_id == friend.id, Referral.paid_at.is_(None)).with_for_update()
        )
        if ref is None:
            return None
        inviter = await self.session.get(User, ref.inviter_id)
        if inviter is None:
            return None
        ref.paid_at = self.clock()
        points = PointsService(self.session, self.clock)
        await points.grant(friend, FRIEND_BONUS, PointsReason.REFERRAL_WELCOME, payment_id=payment_id)
        await points.grant(inviter, INVITER_POINTS, PointsReason.REFERRAL, payment_id=payment_id)
        paid = (
            await self.session.scalar(
                select(func.count())
                .select_from(Referral)
                .where(Referral.inviter_id == inviter.id, Referral.paid_at.is_not(None))
            )
            or 0
        )
        total, milestone, coupon = INVITER_POINTS, None, False
        if paid in MILESTONES:
            milestone = paid
            kind, value = MILESTONES[paid]
            if kind == "coupon":
                self.session.add(Coupon(user_id=inviter.id, slides=SlideTier.S20, origin=CouponOrigin.REFERRAL))
                coupon = True
            else:
                await points.grant(inviter, value, PointsReason.REFERRAL_BONUS, payment_id=payment_id)
                total += value
        ref.points = total
        await self.session.flush()
        return ReferralReward(
            inviter=inviter,
            friend=friend,
            points=total,
            milestone=milestone,
            friend_bonus=FRIEND_BONUS,
            paid_friends=paid,
            coupon=coupon,
        )

    async def summary(self, inviter: User) -> Summary:
        rows = (
            await self.session.execute(
                select(Referral, User)
                .join(User, User.id == Referral.friend_id)
                .where(Referral.inviter_id == inviter.id)
                .order_by(Referral.id.desc())
                .limit(100)
            )
        ).all()
        out = Summary(code=code_for(inviter.id))
        for ref, friend in rows:
            out.friends.append(FriendRow(friend.first_name or "—", ref.created_at, ref.paid_at, ref.points))
            if ref.paid_at is not None:
                out.paid += 1
                out.earned += ref.points
        return out
