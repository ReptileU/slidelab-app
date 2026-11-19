class DomainError(Exception):
    """Ошибка бизнес-правила. `code` уходит клиенту, текст — для логов и менеджера."""

    code = "domain_error"


class NotFoundError(DomainError):
    code = "not_found"


class ForbiddenError(DomainError):
    code = "forbidden"


class InvalidTransitionError(DomainError):
    code = "invalid_transition"


class InsufficientPackageError(DomainError):
    code = "insufficient_package"


class ParallelLimitError(DomainError):
    code = "parallel_limit"


class CoverLimitError(DomainError):
    """Слишком много бесплатных обложек ждут ответа клиента — новую бесплатную не начинаем."""

    code = "cover_limit"
    client_key = "cover_limit"  # клиенту — этот текст, а не общее «что-то пошло не так»


class PaymentRequiredError(DomainError):
    code = "payment_required"


class DueTooSoonError(DomainError):
    """Срок раньше, чем позволяет «Обычно», — такой заказ оформляют как «Срочно»."""

    code = "due_too_soon"
