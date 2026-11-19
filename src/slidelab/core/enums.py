from enum import StrEnum


class Lang(StrEnum):
    RU = "ru"
    UZ = "uz"
    EN = "en"


class SlideTier(StrEnum):
    """Объём презентации: до 15, 16–20, 21–30 слайдов."""

    S10 = "s10"
    S20 = "s20"
    S30 = "s30"


class Deadline(StrEnum):
    URGENT = "urgent"  # +50%, только до 20 слайдов
    NORMAL = "normal"  # к дате, которую выбрал клиент (не раньше чем через NORMAL_MIN_HOURS)
    RELAXED = "relaxed"  # не спешу


class Design(StrEnum):
    OURS = "ours"  # уникальный дизайн под тему
    OWN = "own"  # по шаблону клиента


class OrderStatus(StrEnum):
    NEW = "new"
    COVER = "cover"  # бесплатная обложка отправлена
    AWAITING_PAYMENT = "awaiting_payment"  # клиент согласен, ждём оплату
    WORK = "work"
    DONE = "done"
    REVISION = "revision"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    """Стадия конвейера: что сейчас делает Claude и что ждёт проверки.

    Значения записываются в orders/<id>/status.json — их читает сессия Claude, менять нельзя.
    """

    COVER_TODO = "cover_todo"  # Claude делает обложку
    COVER_REVIEW = "cover_review"  # обложка у админа на проверке
    COVER_SENT = "cover_sent"  # обложка у клиента
    COVER_OK = "cover_ok"  # клиент одобрил, ждём оплату
    DECK_TODO = "deck_todo"  # Claude делает презентацию
    DECK_REVIEW = "deck_review"
    EDIT_TODO = "edit_todo"  # Claude вносит правки
    EDIT_REVIEW = "edit_review"
    DONE = "done"


class OrderSource(StrEnum):
    CHAT = "chat"  # анкета в чате
    APP = "app"  # Mini App
    FILE = "file"  # переслали файл — быстрый заказ


class PaidFrom(StrEnum):
    CASH = "cash"
    PACKAGE = "package"


class PlanCode(StrEnum):
    WEEK = "week"
    MONTH = "month"
    VIP = "vip"
    LUCKY = "lucky"  # бонус-пакет: минимум одна презентация, с шансом на больше


class BoxPrize(StrEnum):
    """Что выпало в бонус-пакете."""

    ONE = "one"  # 1 презентация
    TWO = "two"  # 2 презентации
    FOUR = "four"  # 4 презентации, как пакет на месяц
    VIP = "vip"  # VIP-пакет: 10 презентаций
    COUPONS = "coupons"  # только в пакете за баллы: несколько купонов (каждый — презентация без срока)
    DISCOUNT = "discount"  # только в пакете за баллы: скидка на следующий оплачиваемый заказ
    POINTS = "points"  # только в пакете за баллы: часть баллов вернулась


class PointsReason(StrEnum):
    """Движения по баллам: каждое — строкой в points_ledger."""

    ORDER = "order"  # оплатил заказ деньгами
    PLAN = "plan"  # купил пакет деньгами (за каждую презентацию)
    LUCKY = "lucky"  # купил бонус-пакет деньгами
    GIFT = "gift"  # купил пакет в подарок
    BOX = "box"  # потратил на пакет за баллы
    BOX_PRIZE = "box_prize"  # баллы выпали в пакете за баллы
    EXPIRED = "expired"  # сгорели: полгода без покупок
    GRANT = "grant"  # начислил менеджер


class LedgerReason(StrEnum):
    PURCHASE = "purchase"
    CARRY_OVER = "carry_over"  # остаток старого пакета переносится в новый
    ORDER = "order"  # списание за заказ
    REFUND = "refund"  # возврат при отмене заказа
    GRANT = "grant"  # начислено менеджером
    BONUS = "bonus"  # выпало в бонус-пакете
    GIFT = "gift"  # подарок: минус у дарителя, плюс у получателя


class PaymentProvider(StrEnum):
    STARS = "stars"
    MANUAL_CARD = "manual_card"  # перевод на карту, подтверждает менеджер


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class AttachmentKind(StrEnum):
    SOURCE = "source"  # материалы клиента
    COVER = "cover"
    RESULT = "result"  # готовые PPTX/PDF
    REVISION = "revision"  # скриншоты к правкам


class MessageDirection(StrEnum):
    IN = "in"  # от клиента
    OUT = "out"  # от менеджера


class CouponOrigin(StrEnum):
    """Откуда купон на одну оплаченную презентацию."""

    CANCEL = "cancel"  # отменил оплаченный заказ (или пакет истёк до отмены)
    GIFT = "gift"  # подарили
    BONUS = "bonus"  # выпал в бонус-пакете


class GiftKind(StrEnum):
    COUPON = "coupon"  # купон целиком
    PACK = "pack"  # несколько презентаций из пакета


class GiftStatus(StrEnum):
    PENDING = "pending"  # ссылка отправлена, ещё не забрали
    CLAIMED = "claimed"
    REVOKED = "revoked"  # даритель передумал — вернулось ему
